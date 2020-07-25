#Project inspired by Harmony: https://github.com/pardeike/Harmony

from inspect import getfullargspec, signature as sig, Parameter, ismodule, isclass
from collections.abc import Iterable
from dis import Bytecode

class PatchingError(Exception):pass
class InjectionError(Exception):pass

Patches = []

def checkType(value, t, instance = True):
	if type(t)!=type:raise TypeError('"t" should be a type')
	if (not isinstance(value, t)) if instance else (type(value)!=t):raise TypeError(f"Value should be {t.__name__}")
	return value

class OptionalYield:		#Parent class for types that can be yielded optionally
	def __init__(self, _yield):
		self.Yield = checkType(_yield, bool)

class SetVar(OptionalYield):	#Handles parameter  change
	def __init__(self, name, value, _yield = False):
		super().__init__(_yield)
		self.Name = checkType(name, str)
		self.Value = value
		
class Stop(OptionalYield):		#Stop iteration
	def __init__(self, state, _yield = False):
		super().__init__(_yield)
		self.State = checkType(state, bool)

def Patch(t, name, force = False):				#t = Class to patch, name = method to patch
	if not isclass(t) and not ismodule(t):raise PatchingError(f"Patch type should either be a type or a module. Current type: {type(t)}")
	def PatchWrapper(cl):		#cl = Patching class
		if not isclass(cl):raise PatchingError("Patch decorator should be applied to classes only!")
		if type(force)!=bool:raise TypeError('"force" should be a boolean')
		def HandlePatch():
			if not hasattr(t, name):raise PatchingError(f'Method with name "{name}" does not exist in class "{t.__name__}"')
			global original
			original = getattr(t, name)
			oldOriginal = getattr(t, name)
			def selectArgs(base, func, kargs) -> dict:		#Selects the parameters that a function needs
				if kargs:return base
				final = {}
				for arg in getfullargspec(func).args:
					if arg in base:final[arg]=base[arg]
				return final
			def getFieldNames(func, prefix) -> list:		#From the list of parameters returns the one that represents a field name
				final = []
				for arg in getfullargspec(func).args:
					if arg.startswith(f"{prefix}_"):final.append(arg.replace(f"{prefix}_","",1))
				return final
			def getDefaultArgs(func):
					signature = sig(func)
					return {
						k: v.default
						for k, v in signature.parameters.items()
						if v.default is not Parameter.empty
					}
			class RefVar:	#Used to indicate the patcher that this variable is modified type-side
				def __init__(self, name, value):
					self.Name = checkType(name, str)
					self.Value = value
			def PatchedMethod(*args, **kwargs):
				global original
				global RunOriginal
				arginfo = getfullargspec(oldOriginal)
				params = arginfo.args
				kwarg = arginfo.varkw != None
				infarg = arginfo.varargs != None
				pos = -1
				argPrefix = f"_{cl.__name__}__"
				arguments = {f"{argPrefix}result":None, f"{argPrefix}state":None}
				defaults = getDefaultArgs(oldOriginal)
				r = None
				for parameter in params:
					pos+=1
					pName = parameter
					try:param = args[pos]
					except IndexError:
						if pName in defaults:param = defaults[pName]
						elif force and len(params)-len(args)==1 and params[0]=="self":arguments["self"]=None
						else:r = PatchingError(f'Method "{name}" expects {len(params)} arguments, {len(args)} were given.')
					#if pName=="self" and type(param)!=t:raise TypeError("Invalid instance class")
					arguments[pName]=param
				other = args[pos+1:] if pos<len(args)-1 else []		#*args support
				if r!=None:raise r
				if kwarg:arguments.update(kwargs)
				hasPrefix = hasattr(cl, "prefix")
				hasPostfix = hasattr(cl, "postfix")
				hasFinalizer = hasattr(cl, "finalizer")
				prefix = getattr(cl, "prefix") if hasPrefix else None
				postfix = getattr(cl, "postfix") if hasPostfix else None
				finalizer = getattr(cl, "finalizer") if hasFinalizer else None
				if hasattr(cl, "transpiler"):		#Handle transpiler
					original = getattr(cl, "transpiler")
					arginfo = getfullargspec(original)
					params = arginfo.args
					kwarg = arginfo.varkw != None
				arguments[f"{argPrefix}originalMethod"] = oldOriginal
				arguments[f"{argPrefix}instance"] = arguments["self"] if "self" in arguments else None
				prefkw = getfullargspec(prefix).varkw!=None if hasPrefix else False
				postkw = getfullargspec(postfix).varkw!=None if hasPostfix else False
				finalkw = getfullargspec(finalizer).varkw!=None if hasFinalizer else False
				yields = []
				RunOriginal = 1
				setter = arguments["self"] if "self" in arguments else t		#If there's no object reference, use type
				def getName(base):		#Gets the name to use on injections
					if base.startswith("__"):base = base.replace("__",argPrefix,1)
					return base
				def getArguments(base):		#Handles RefVar values
					final = {}
					for key in base:final[key] = base[key].Value if isinstance(base[key], RefVar) else base[key]
					return final
				def handleChange(name, value, paramSet):		#Handles parameter change
					name = checkType(name, str)
					if not name in paramSet or not name in arguments:
						temp = f"{argPrefix}{name}"				#Check if it's an injected variable
						if temp in paramSet and temp in arguments:
							handleChange(temp, value, paramSet)
							return
						temp = f"{argPrefix}_{name}"			#Check if it's a field injection
						if temp in paramSet and temp in arguments:
							handleChange(temp, value, paramSet)
							return
						raise NameError(f'Invalid parameter name: "{name}"')
					if isinstance(arguments[name], RefVar):
						setattr(setter, arguments[name].Name, value)
						arguments[name]=RefVar(arguments[name].Name, value)
					else:arguments[name]=value
				def getPrivate(func):	#Refer fields
					for field in getFieldNames(func, argPrefix):
						if not hasattr(setter, field):raise InjectionError(f'Invalid variable name: {field}')
						arguments[f"{argPrefix}_{field}"]=RefVar(field, getattr(setter, field))
				def runIteration(func, stop, *o, **kargs):		#Runs prefix and postfix
					global RunOriginal
					paramSet = [x for x in kargs]
					o = o if getfullargspec(func).varargs!=None else []
					ran = func(*o, **kargs)
					if isinstance(ran, Iterable):			#Check if there's anything yielded
						for value in ran:
							if isinstance(value, OptionalYield) and value.Yield:yields.append(value)	#Handle every OptionalYield instance
							else:yields.append(value)
							if isinstance(value, Stop):		#Handle Stop
								if not value.State and stop:RunOriginal-=1
								break
							if isinstance(value, SetVar):	#Handle SetVar
								handleChange(getName(value.Name), value.Value, paramSet)
					return ran
				def runPrefix(*o, **kargs):
					runIteration(prefix, True, *o, **kargs)
				def runOriginal(*o, **kargs):
					arguments[f"{argPrefix}result"]=runIteration(original, False, *o, **kargs)
				def runPostfix(*o, **kargs):
					runIteration(postfix, False, *o, **kargs)
				r = None
				try:
					if hasPrefix:
						getPrivate(prefix)
						runPrefix(*other, **getArguments(selectArgs(arguments, prefix, prefkw)))
						yields = []
					if RunOriginal:
						argsWithInst = arguments.copy()
						argsWithInst[f"{argPrefix}instructions"]=Bytecode(oldOriginal)
						runOriginal(*other, **getArguments(selectArgs(argsWithInst, original, kwarg)))
						yields = []
					if hasPostfix:
						getPrivate(postfix)
						runPostfix(*other, **getArguments(selectArgs(arguments, postfix, postkw)))
						yields = []
				except Exception as e:
					if hasFinalizer:		#Handle finalizer
						ex = finalizer(**selectArgs({f"{argPrefix}exception":e}, finalizer, finalkw))
						if isinstance(ex, Exception):r = ex
					else:r = e
				if r!=None:raise r
				return arguments[f"{argPrefix}result"]		#Return result
			try:setattr(t, name, PatchedMethod)		#Patch
			except TypeError:		#Built-in methods
				from forbiddenfruit import curse
				curse(t, name, PatchedMethod)
		Patches.append(HandlePatch)		#Ready to patch
	return PatchWrapper		#Decorator added






def PatchIter(t, name, force = False):			#Love you, Python, making functions generators if there's a yield keyword in it, no matter if it's used or not
	if not isclass(t) and not ismodule(t):raise PatchingError(f"Patch type should either be a type or a module. Current type: {type(t)}")
	def PatchWrapper(cl):
		if not isclass(cl):raise PatchingError("Patch decorator should be applied to classes only!")
		if type(force)!=bool:raise TypeError('"force" should be a boolean')
		def HandlePatch():
			if not hasattr(t, name):raise PatchingError(f'Method with name "{name}" does not exist in class "{t.__name__}"')
			global original
			original = getattr(t, name)
			oldOriginal = getattr(t, name)
			def selectArgs(base, func, kargs) -> dict:
				if kargs:return base
				final = {}
				for arg in getfullargspec(func).args:
					if arg in base:final[arg]=base[arg]
				return final
			def getFieldNames(func, prefix) -> list:
				final = []
				for arg in getfullargspec(func).args:
					if arg.startswith(f"{prefix}_"):final.append(arg.replace(f"{prefix}_","",1))
				return final
			def getDefaultArgs(func):
					signature = sig(func)
					return {
						k: v.default
						for k, v in signature.parameters.items()
						if v.default is not Parameter.empty
					}
			class RefVar:
				def __init__(self, name, value):
					self.Name = checkType(name, str)
					self.Value = value
			def PatchedMethod(*args, **kwargs):
				global original
				global RunOriginal
				arginfo = getfullargspec(oldOriginal)
				params = arginfo.args
				kwarg = arginfo.varkw != None
				pos = -1
				argPrefix = f"_{cl.__name__}__"
				arguments = {f"{argPrefix}result":None, f"{argPrefix}state":None}
				defaults = getDefaultArgs(oldOriginal)
				r = None
				for parameter in params:
					pos+=1
					pName = parameter
					try:param = args[pos]
					except IndexError:
						if pName in defaults:param = defaults[pName]
						elif force and len(params)-len(args)==1 and params[0]=="self":arguments["self"]=None
						else:r = PatchingError(f'Method "{name}" expects {len(params)} arguments, {len(args)} were given.')
					#if pName=="self" and type(param)!=t:raise TypeError("Invalid instance class")
					arguments[pName]=param
				other = args[pos+1:] if pos<len(args)-1 else []
				if r!=None:raise r
				if kwarg:arguments.update(kwargs)
				arguments[f"{argPrefix}originalMethod"] = oldOriginal
				arguments[f"{argPrefix}instance"] = arguments["self"] if "self" in arguments else None
				hasPrefix = hasattr(cl, "prefix")
				hasPostfix = hasattr(cl, "postfix")
				hasFinalizer = hasattr(cl, "finalizer")	
				prefix = getattr(cl, "prefix") if hasPrefix else None
				postfix = getattr(cl, "postfix") if hasPostfix else None
				finalizer = getattr(cl, "finalizer") if hasFinalizer else None
				if hasattr(cl, "transpiler"):
					original = getattr(cl, "transpiler")
					arginfo = getfullargspec(original)
					params = arginfo.args
					kwarg = arginfo.varkw != None
				prefkw = getfullargspec(prefix).varkw!=None if hasPrefix else False
				postkw = getfullargspec(postfix).varkw!=None if hasPostfix else False
				finalkw = getfullargspec(finalizer).varkw!=None if hasFinalizer else False
				yields = []
				RunOriginal = 1
				setter = arguments["self"] if "self" in arguments else t
				def getName(base):
					if base.startswith("__"):base = base.replace("__",argPrefix,1)
					return base
				def getArguments(base):
					final = {}
					for key in base:final[key] = base[key].Value if isinstance(base[key], RefVar) else base[key]
					return final
				def handleChange(name, value, paramSet):
					name = checkType(name, str)
					if not name in paramSet or not name in arguments:
						temp = f"{argPrefix}{name}"
						if temp in paramSet and temp in arguments:
							handleChange(temp, value, paramSet)
							return
						temp = f"{argPrefix}_{name}"
						if temp in paramSet and temp in arguments:
							handleChange(temp, value, paramSet)
							return
						raise NameError(f'Invalid parameter name: "{name}"')
					if isinstance(arguments[name], RefVar):
						setattr(setter, arguments[name].Name, value)
						arguments[name]=RefVar(arguments[name].Name, value)
					else:arguments[name]=value
				def getPrivate(func):
					for field in getFieldNames(func, argPrefix):
						if not hasattr(setter, field):raise InjectionError(f'Invalid variable name: {field}')
						arguments[f"{argPrefix}_{field}"]=RefVar(field, getattr(setter, field))
				def runIteration(func, stop, *o, **kargs):
					global RunOriginal
					paramSet = [x for x in kargs]
					o = o if getfullargspec(func).varargs!=None else []
					ran = func(*o, **kargs)
					if isinstance(ran, Iterable):
						for value in ran:
							if isinstance(value, OptionalYield) and value.Yield:yield value
							else:yield value
							if isinstance(value, Stop):
								if not value.State and stop:RunOriginal-=1
								break
							if isinstance(value, SetVar):
								handleChange(getName(value.Name), value.Value, paramSet)
					return ran
				def runPrefix(*o, **kargs):
					ran = runIteration(prefix, True, *o, **kargs)
					if isinstance(ran, Iterable):
						for value in ran:yield value
				def runOriginal(*o, **kargs):
					ran=runIteration(original, False, *o, **kargs)
					arguments[f"{argPrefix}result"]=ran
					if isinstance(ran, Iterable):
						for value in ran:yield value
				def runPostfix(*o, **kargs):
					ran = runIteration(postfix, True, *o, **kargs)
					if isinstance(ran, Iterable):
						for value in ran:yield value
				r = None
				try:
					if hasPrefix:
						getPrivate(prefix)
						ran =runPrefix(*other, **getArguments(selectArgs(arguments, prefix, prefkw)))
						if isinstance(ran, Iterable):
							for value in ran:yield value
					if RunOriginal:
						argsWithInst = arguments.copy()
						argsWithInst[f"{argPrefix}instructions"]=Bytecode(oldOriginal)
						ran = runOriginal(*other, **getArguments(selectArgs(argsWithInst, original, kwarg)))
						if isinstance(ran, Iterable):
							for value in ran:yield value
						yields = []
					if hasPostfix:
						getPrivate(postfix)
						ran = runPostfix(*other, **getArguments(selectArgs(arguments, postfix, postkw)))
						if isinstance(ran, Iterable):
							for value in ran:yield value
				except Exception as e:
					if hasFinalizer:
						ex = finalizer(**selectArgs({f"{argPrefix}exception":e}, finalizer, finalkw))
						if isinstance(ex, Iterable):
							for value in ex:
								if isinstance(value, Exception):
									r = value
									break
								yield value
						if isinstance(ex, Exception):r = ex
					else:r = e
				if r!=None:raise r
				return arguments[f"{argPrefix}result"]
			try:setattr(t, name, PatchedMethod)
			except TypeError:
				from forbiddenfruit import curse
				curse(t, name, PatchedMethod)
		Patches.append(HandlePatch)
	return PatchWrapper

def PatchAll():
	global Patches
	for p in Patches:p()		#Run every HandlePatch() method
	Patches = []		#Clear patch methods

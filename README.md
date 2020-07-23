# A Python patching module inspired by [Harmony](https://github.com/pardeike/Harmony)

With this module, you can alter live methods or functions of classes and modules.

## Dependencies

-[Forbiddenfruit](https://pypi.org/project/forbiddenfruit/) (Only needed if you patch methods of built-in *classes* (like str, int, etc.))

## Injection

To inject the patches into a builded program, use the [pyrasite](https://pypi.org/project/pyrasite/) library

## Usage

Use the `Patch` decorator on a class with the following arguments to patch a method:

| Name | Type | Default value | Description |
| --- | --- | --- | --- |
| t | `type` or `module` | - | The type or module that contains the target method |
| name | `str` | - | The name of the target method |
| force | `bool` | False | If true, the patch will try to add a `None` as object reference if the method needs it and it isn't provided. More about it [here](https://github.com/Qkrisi/python-patcher/wiki/Safe-Patching) |

The class the decorator is applied to can contain any of the following patch methods (or more of them):

| Name | Description |
| --- | --- |
| Prefix | Runs before the original method |
| Transpiler | Alters the original method |
| Postfix | Runs after the original method |
| Finalizer | Catches an exception thrown in the other 3 |

To execute the patches, call the `PatchAll()` method!

*Note*: `*args` and `**kwargs` parameters are supported!

**For a full documentation and parameter injections, please visit the [wiki page](https://github.com/qkrisi/python-patcher/wiki)!**

## Example

Basic patch:

```py
from Patcher import *

class TargetClass:
	def TargetMethod():
		print("This is the original method")
		
@Patch(TargetClass, "TargetMethod")
class Patch1:
	def prefix():
		print("This is the prefix")
		
	def postfix():
		print("This is the postfix")
		
PatchAll()

TargetClass.TargetMethod()

'''
Output:
This is the prefix
This is the original method
This is the postfix
'''
```

Instance patch:

```py
from Patcher import *

class TargetClass:
	def __init__(self, p):
		self.P = p

	def TargetMethod(self):
		print(f"This is my p variable: {self.P}")

@Patch(TargetClass, "TargetMethod")
class Patch1:
	def prefix(__instance, ___P):
		print(f"Prefix called: {__instance.P}, {___P}")
		print("Modifying parameter")
		yield SetVar("___P", "This is a modified variable")		#"___" is negligible

PatchAll()

TargetClass("This is a variable").TargetMethod()

'''
Output:
Prefix called: This is a variable, This is a variable
Modifying parameter
This is my p variable: This is a modified variable
'''
```

Save state, skip original, alter result:

```py
from Patcher import *

class TargetClass:
	def TargetMethod():
		return "This is the original method"

@Patch(TargetClass, "TargetMethod")
class Patch1:
	def prefix(__state):
		yield SetVar("state", "This is the modified method")
		yield Stop(False)
	
	def postfix(__state, __result):
		yield SetVar("result", __state)

PatchAll()

print(TargetClass.TargetMethod())

#Output: This is the modified method
```

Patch method in module:

```py
#ModuleToPatch

def TargetMethod():
	return "This is the original method"
	
def start():
	print(TargetMethod())
```
```py
#File1

from Patcher import *
import ModuleToPatch

@Patch(ModuleToPatch, "TargetMethod")			#Use @Patch(__import__(__name__), "TargetMethod") to patch a method in the self module!
class Patch1:
	def prefix(__result):
		yield SetVar("result", "This is the modified method")
		yield Stop(False)

PatchAll()

ModuleToPatch.start()

#Output: This is the modified method
```

**For more examples, please look at the [wiki page](https://github.com/qkrisi/python-patcher/wiki)!**

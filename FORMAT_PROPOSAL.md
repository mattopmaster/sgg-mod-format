# Proposal of a new format for modular mods

======
## Why?

There are a few reasons to change the mod format going forward:
* with the current format it's not possible to make a mod that has independent modules that can be toggled on an off from the user
* the current format for sjson changes is convoluted, hard to read and not concise
* the current format has little room for extensions for future updates
======
## Proposal

------
### Modfile

The current _modfile.txt_ is changed to _modfile.sjson_, and has a fixed structure, as described below
Simple imports would be changed from:
```
Import "foo.lua"
```
to:
```
{
    Import = "foo.lua"
}
```
For multiple single imports:
```
{
    Import = [ "foo.lua", "bar.lua", "etc.lua" ]
}
```
To import all files in a folder:
```
{
    Import = "foo/*"
}
```
Comments would follow the sjson comment rules.
```
/* This is a comment!! */
```
The properties **To** and **Load Priority** are renamed to **Target** and **LoadPriority** respectively, and follow the same structure as above:
```
{
    Import = "foo.lua"
    LoadPriority = 42
    Target = "bar.lua"
}
```
**Import** becomes the only keyword used to import files, with **Type** being introduced to specify the file type. If the **Type** property is not defined, it defaults to `lua`
```
{
    Import = "foo.sjson"
    Type = "sjson"
    Target = "foo/bar.sjson"
}
```
To define multiple import rules, we just separate them with a comma:
```
{
    Import = "foo.lua"
},
{
    Import = "bar.lua"
}
```
A new property **IfConfig** is introduced, which makes the rule conditional on the config file (config file described in the next section)
```
{
    IfConfig = "foo"
    Import = "bar"
}
```
------
### Config

A new optional file is added in the root folder of the mod, which must be named _config.sjson_. Its structure would be:
```
{
    foo = true
    bar = false
    SemanticallySignificantModuleName = true
}
```
The values in this file allow to enable/disable modules of the mod.
If the file is parsed incorrectly or is missing, and a rule with the **IfConfig** property is present, the value defaults to `true`, and a warning is displayed on the console
------
### SJSON

The current structure is scrapped entirely, to allow a more readable and concise structure to be used.
The new structure would consist in rules that have 4 properties: **TreePath**, **Mode**, **Value** and **Key**.
**TreePath** has value equal to the path taken in the tree representation of the target sjson to reach the desired node, inclusive. Each node present in the path is separated with `::`. A value equal to `::` refers to the root of the tree (the entire target).
**Mode** is a value between `Delete`, `Update` and `Append`
**Value** is the value used when in mode `Update` or `Append` and defines the value to be used when doing said operation
**Key** is the value used when in mode `Append`. This property is ignored when doing an append operation on an element that has sequential index key
```
{
    TreePath = "foo::bar::42"
    Mode = "Update"
    Value = {
        Title = "Cool change"
        Description = "With an even cooler description"
    }
},
{
    TreePath = "foo::bar"
    Mode = "Append"
    Value = {
        Title = "Cool title number 2"
        Description = "But where is number 1?"
    }
},
{
    TreePath = "foo::bar::42::Title"
    Mode = "Update"
    Value = "Cool title number 1"
}
```
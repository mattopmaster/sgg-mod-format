"""
Mod Importer for SuperGiant Games' Games

https://github.com/MagicGonads/sgg-mod-format
"""

__all__ = [
    # functions
    "main",
    "configure_globals",
    "start",
    "preplogfile",
    "cleanup",
    "hashfile",
    "lua_addimport",
    "sjson_safeget",
    "sjson_clearDNE",
    "sjson_read",
    "sjson_write",
    "sjson_map",
    "sjson_merge",
    # variables
    "configfile",
    "logfile_prefix",
    "logfile_suffix",
    "edited_suffix",
    "scopemods",
    "modsrel",
    "baserel",
    "editrel",
    "logsrel",
    "gamerel",
    "do_log",
    "cfg_modify",
    "cfg_overwrite",
    "profile_use_special",
    # modules
    "logging",
    "sjson",
    "hashlib",
    # other
    "DNE",
]
__version__ = "1.0a-r4"
__author__ = "Andre Issa"

# Dependencies

import os, sys, stat
import logging
import warnings
import hashlib
from getopt import getopt
from pathlib import Path
from shutil import copyfile, rmtree
from datetime import datetime
from collections import defaultdict, OrderedDict
from distutils.dir_util import copy_tree
from distutils.errors import DistutilsFileError

from sggmi import util

## Importer Config

import json

## SJSON Handling
try:
    import sjson
except ModuleNotFoundError:
    sjson = None
    
## DEPPTH package patching

try:
    from deppth import deppth
except ModuleNotFoundError:
    deppth = None

# Configurable Globals

configfile = "miconfig.yml"
#### These are better configured using the config file to be specific to different installs
scopemods = "Deploy"  # Must be accessible to game scope
modsrel = "Mods"
baserel = "Base Cache"
editrel = "Edit Cache"
logsrel = "Logs"
logfile_prefix = "log-modimp "
logfile_suffix = ".txt"
edited_suffix = ".hash"

# Data Functionality

DNE = ()  # 'Does Not Exist' singleton

## General file payloads

def file_replace(base, path):
    copyfile(path, base)

## LUA import statement adding

def lua_import(base, path):
    with alt_open(base, "a") as basefile:
        basefile.write('\nImport "../' + path + '"')

def lua_import_top(base,path):
    with alt_open(base,'r+') as basefile:
        lines = basefile.readlines()     
        lines.insert(0, "Import "+"\""+modsrel+"/"+path+"\"\n")  
        basefile.seek(0)                 
        basefile.writelines(lines)

## Packages

if deppth is not None:
    def package_patch(base, path):
        deppth.patch(base,path)

def package_copy(base,path):
    if os.path.exists(base):
        copyfile(path, base)

## SJSON mapping

if sjson is not None:

    sjson_RESERVED_sequence = "_sequence"
    sjson_RESERVED_append = "_append"
    sjson_RESERVED_replace = "_replace"
    sjson_RESERVED_delete = "_delete"
    sjson_RESERVED_key = "_key"
    sjson_RESERVED_value = "_value"

    def sjson_safeget(data, key):
        if isinstance(data, list):
            if isinstance(key, int):
                if key < len(data) and key >= 0:
                    return data[key]
            return DNE
        if isinstance(data, OrderedDict):
            return util.get_attribute(key, DNE)
        return DNE

    def sjson_clearDNE(data):
        if isinstance(data, OrderedDict):
            for k, v in data.items():
                if v is DNE:
                    del data[k]
                    continue
                data[k] = sjson_clearDNE(v)
        if isinstance(data, list):
            L = []
            for i, v in enumerate(data):
                if v is DNE:
                    continue
                L.append(sjson_clearDNE(v))
            data = L
        return data

    def sjson_read(filename):
        try:
            return sjson.loads(alt_open(filename).read())
        except sjson.ParseException as e:
            alt_print(repr(e))
            return DNE

    def sjson_write(filename, content):
        if not isinstance(filename, str):
            return
        if isinstance(content, OrderedDict):
            content = sjson.dumps(content, 2)
        else:
            content = ""
        with alt_open(filename, "w") as f:
            f.write(content)

    def sjson_map(indata, mapdata):
        if mapdata is DNE:
            return indata
        if sjson_safeget(mapdata, sjson_RESERVED_sequence):
            S = []
            for k, v in mapdata.items():
                try:
                    d = int(k) - len(S)
                    if d >= 0:
                        S.extend([DNE] * (d + 1))
                    S[int(k)] = v
                except ValueError:
                    continue
            mapdata = S
        if type(indata) == type(mapdata):
            if sjson_safeget(mapdata, 0) != sjson_RESERVED_append or isinstance(
                mapdata, OrderedDict
            ):
                if isinstance(mapdata, list):
                    if sjson_safeget(mapdata, 0) == sjson_RESERVED_delete:
                        return DNE
                    if sjson_safeget(mapdata, 0) == sjson_RESERVED_replace:
                        del mapdata[0]
                        return mapdata
                    indata.expand([DNE] * (len(mapdata) - len(indata)))
                    for k, v in enumerate(mapdata):
                        indata[k] = sjson_map(sjson_safeget(indata, k), v)
                else:
                    if sjson_safeget(mapdata, sjson_RESERVED_delete):
                        return DNE
                    if sjson_safeget(mapdata, sjson_RESERVED_replace):
                        del mapdata[sjson_RESERVED_replace]
                        return mapdata
                    for k, v in mapdata.items():
                        indata[k] = sjson_map(sjson_safeget(indata, k), v)
                return indata
            elif isinstance(mapdata, list):
                for i in range(1, len(mapdata)):
                    indata.append(mapdata[i])
                return indata
        else:
            return mapdata
        return mapdata

    def sjson_merge(infile, mapfile):
        indata = sjson_read(infile)
        if mapfile:
            mapdata = sjson_read(mapfile)
        else:
            mapdata = DNE
        indata = sjson_map(indata, mapdata)
        indata = sjson_clearDNE(indata)
        sjson_write(infile, indata)


else:

    sjson_safeget = None
    sjson_clearDNE = None
    sjson_read = None
    sjson_write = None
    sjson_map = None
    sjson_merge = None

# FILE/MOD CONTROL


class Signal:
    truth = False
    message = None

    def __init__(self, truth=False, message=None):
        self.truth = truth
        self.message = message

    def __bool__(self):
        return self.truth

    def __eq__(self, other):
        if isinstance(other, Signal):
            return (self.truth, self.message) == (other.truth, other.message)
        return False

    def __str__(self):
        return str(self.message)

    def __repr__(self):
        return (
            self.__class__.__name__
            + "("
            + self.truth.__repr__()
            + ","
            + self.message.__repr__()
            + ")"
        )


hashes = ["md5"]


def hashfile(file, out=None, modes=hashes, blocksize=65536):
    lines = []
    for mode in modes:
        hasher = hashlib.new(mode)
        with alt_open(file, "rb") as afile:
            buf = afile.read(blocksize)
            while len(buf) > 0:
                hasher.update(buf)
                buf = afile.read(blocksize)
            lines.append(mode + "\t" + hasher.hexdigest())
    content = "\n".join(lines)
    if out:
        with alt_open(out, "w") as ofile:
            ofile.write(content)
    return content


def is_subfile(filename, folder):
    if os.path.exists(filename):
        if os.path.commonprefix([filename, folder]) == folder:
            if os.path.isfile(filename):
                return Signal(True, "SubFile")
            return Signal(False, "SubDir")
        return Signal(False, "NonSub")
    return Signal(False, "DoesNotExist")


def in_scope(filename, permit_DNE=False):
    if os.path.exists(filename) or permit_DNE:
        if local_in_scope:
            tfile = filename[len(os.path.commonprefix([filename, localdir])) :]
            tfile = tfile.split("/")[1]
            if tfile in localsources:
                return Signal(False, "IsLocalSource")
        if base_in_scope:
            if os.path.commonprefix([filename, basedir]) == basedir:
                return Signal(False, "InBase")
        if edit_in_scope:
            if os.path.commonprefix([filename, editdir]) == editdir:
                return Signal(False, "InEdits")
        if os.path.commonprefix([filename, scopedir]) == scopedir:
            if os.path.isfile(filename):
                return Signal(True, "FileInScope")
            return Signal(False, "DirInScope")
        return Signal(False, "OutOfScope")
    return Signal(False, "DoesNotExist")


def alt_print(*args, **kwargs):
    if do_echo:
        return print(*args, **kwargs)
    if do_log:
        tlog = logsdir + "/" + "temp-" + logfile_prefix + thetime() + logfile_suffix
        f = alt_open(tlog, "w")
        print(file=f, *args, **kwargs)
        f.close()
        f = alt_open(tlog, "r")
        data = f.read()
        f.close()
        os.remove(tlog)
        return logging.getLogger(__name__).info(data)


def alt_warn(message):
    warnings.warn(message, stacklevel=2)
    if do_log and do_echo:
        logging.getLogger(__name__).warning(message)

def alt_open(*args,**kwargs):
    return open(*args,encoding='utf-8',**kwargs)

def alt_input(*args, **kwargs):
    if do_echo:
        if do_input:
            return input(*args)
        print(*args)
        return kwargs.get("default", None)
    if do_log:
        tlog = logsdir + "/" + "temp-" + logfile_prefix + thetime() + logfile_suffix
        f = alt_open(tlog, "w")
        print(file=f, *args)
        f.close()
        f = alt_open(tlog, "r")
        data = f.read()
        f.close()
        os.remove(tlog)
        logging.getLogger(__name__).info(data)
        if do_input:
            return input()
        return kwargs.get("default", None)


def alt_exit(code=None):
    alt_input("Press any key to end program...")
    exit(code)


def modfile_splitlines(body):
    glines = map(lambda s: s.strip().split('"'), body.split("\n"))
    lines = []
    li = -1
    mlcom = False

    def gp(group, lines, li, mlcom, even):
        if mlcom:
            tgroup = group.split(modfile_mlcom_end, 1)
            if len(tgroup) == 1:  # still commented, carry on
                even = not even
                return (lines, li, mlcom, even)
            else:  # comment ends, if a quote, even is disrupted
                even = False
                mlcom = False
                group = tgroup[1]
        if even:
            lines[li] += '"' + group + '"'
        else:
            tgroup = group.split(modfile_comment, 1)
            tline = tgroup[0].split(modfile_mlcom_start, 1)
            tgroup = tline[0].split(modfile_linebreak)
            lines[li] += tgroup[0]  # uncommented line
            for g in tgroup[1:]:  # new uncommented lines
                lines.append(g)
                li += 1
            if len(tline) > 1:  # comment begins
                mlcom = True
                lines, li, mlcom, even = gp(tline[1], lines, li, mlcom, even)
        return (lines, li, mlcom, even)

    for groups in glines:
        even = False
        li += 1
        lines.append("")
        for group in groups:
            lines, li, mlcom, even = gp(group, lines, li, mlcom, even)
            even = not even
    return lines


def modfile_tokenise(line):
    groups = line.strip().split('"')
    for i, group in enumerate(groups):
        if i % 2:
            groups[i] = [group]
        else:
            groups[i] = group.replace(" ", modfile_delimiter)
            groups[i] = groups[i].split(modfile_delimiter)
    tokens = []
    for group in groups:
        for x in group:
            if x != "":
                tokens.append(x)
    return tokens


class Mod:
    """ modcode data structure """

    mode = ""

    def __init__(self, src, data, mode, key, index, **load):
        self.src = src
        self.data = data
        self.mode = mode
        self.key = key
        self.id = index
        self.load = {"priority": default_priority}
        self.load.update(load)


# FILE/MOD LOADING


def modfile_startswith(tokens, keyword, n):
    return tokens[: len(keyword)] == keyword and len(tokens) >= len(keyword) + 1


def modfile_loadcommand(reldir, tokens, to, n, mode, cfg={}, **load):
    for scopepath in to:
        path = scopedir + "/" + scopepath
        if in_scope(path):
            args = [tokens[i::n] for i in range(n)]
            for i in range(len(args[-1])):
                sources = [
                    reldir + "/" + arg[i].replace('"', "").replace("\\", "/")
                    for arg in args
                ]
                paths = []
                num = -1
                for source in sources:
                    if os.path.isdir(modsdir + "/" + source):
                        tpath = []
                        for file in os.scandir(source):
                            file = file.path.replace("\\", "/")
                            if in_scope(file):
                                tpath.append(file)
                        paths.append(tpath)
                        if num > len(tpath) or num < 0:
                            num = len(tpath)
                    elif in_scope(modsdir + "/" + source):
                        paths.append(source)
                if paths:
                    for j in range(abs(num)):
                        sources = [x[j] if isinstance(x, list) else x for x in paths]
                        for src in sources:
                            todeploy[src] = util.merge_dict(todeploy.get(src), cfg)
                        f = lambda x: map(lambda y: deploy_from_scope + "/" + y, x)
                        codes[scopepath].append(
                            Mod(
                                "\n".join(sources),
                                tuple(f(sources)),
                                mode,
                                scopepath,
                                len(codes[scopepath]),
                                **load
                            )
                        )

def modfile_payloadcheck(payload,data):
    if modfile_startswith(data.tokens, modfile_payloads[payload][1], modfile_payloads[payload][2]):
        if len(modfile_payloads[payload])>4:
            if not modfile_payloads[payload][3]:
                alt_warn(modfile_payloads[payload][4]+data.line)
                return True
        modfile_loadcommand(data.reldir, data.tokens[len(modfile_payloads[payload][1]) :],
                            data.to, modfile_payloads[payload][2], payload, data.cfg, **(data.load))
        return True
    return False

def modfile_load(filename, echo=True):
    sig = is_subfile(filename, modsdir)
    if sig:
        prefix = os.path.commonprefix([filename, modsdir])
        relname = filename[len(prefix) + 1 :]
        try:
            file = alt_open(filename, "r")
        except IOError:
            return
        if echo:
            alt_print(relname)

        reldir = "/".join(relname.split("/")[:-1])
        p = default_priority
        to = default_target
        cfg = {}

        with file:
            for line in modfile_splitlines(file.read()):
                tokens = modfile_tokenise(line)
                if len(tokens) == 0:
                    continue
                if modfile_startswith(tokens, modfile_keywords["to"], 0):
                    to = [s.replace("\\", "/") for s in tokens[1:]]
                    if len(to) == 0:
                        to = default_target
                    continue
                if modfile_startswith(tokens, modfile_keywords["load"], 0):
                    n = len(modfile_keywords["load"]) + len(modfile_keywords["priority"])
                    if tokens[len(modfile_keywords["load"]) : n] == modfile_keywords["priority"]:
                        if len(tokens) > n:
                            try:
                                p = int(tokens[n])
                            except ValueError:
                                pass
                        else:
                            p = default_priority
                    continue
                if modfile_startswith(tokens, modfile_keywords["include"], 1):
                    for s in tokens[1:]:
                        modfile_load(
                            reldir + "/" + s.replace('"', "").replace("\\", "/"), echo
                        )
                    continue
                if modfile_startswith(tokens, modfile_keywords["deploy"], 1):
                    for s in tokens[1:]:
                        check = is_subfile(s, modsdir)
                        if check:
                            todeploy[s] = util.merge_dict(todeploy.get(s), cfg)
                        elif check.message == "SubDir":
                            for f in os.scandir(s):
                                S = f.path.replace("\\", "/")
                                todeploy[S] = util.merge_dict(todeploy.get(S), cfg)
                    continue
                data = {
                    "reldir" : reldir,
                    "tokens" : tokens,
                    "to" : to,
                    "cfg" : cfg,
                    "load" : { "priority" : p },
                    "line" : line
                }
                for payload in modfile_payloads.keys():
                    if modfile_payloadswitch(payload,data):
                        break

    elif sig.message == "SubDir":
        for file in os.scandir(filename):
            modfile_load(file.path.replace("\\", "/"), echo)


def is_edited(base):
    if os.path.isfile(editdir + "/" + base + edited_suffix):
        efile = alt_open(editdir + "/" + base + edited_suffix, "r")
        data = efile.read()
        efile.close()
        return data == hashfile(scopedir + "/" + base)
    return False


def deploy_mods():
    for fs, cfg in todeploy.items():
        Path(deploydir + "/" + "/".join(fs.split("/")[:-1])).mkdir(
            parents=True, exist_ok=True
        )
        copyfile(modsdir + "/" + fs, deploydir + "/" + fs)


def sort_mods(base, mods):
    codes[base].sort(key=lambda x: x.load["priority"])
    for i in range(len(mods)):
        mods[i].id = i


def make_base_edits(base, mods, echo=True):
    Path(basedir + "/" + "/".join(base.split("/")[:-1])).mkdir(
        parents=True, exist_ok=True
    )
    copyfile(scopedir + "/" + base, basedir + "/" + base)
    if echo:
        i = 0
        alt_print("\n" + base)

    try:
        for mod in mods:
            modfile_payloads[mod.mode][0](scopedir + "/" + base, mod.data)
            if echo:
                k = i + 1
                for s in mod.src.split("\n"):
                    i += 1
                    alt_print(
                        " #"
                        + str(i)
                        + " +" * (k < i)
                        + " " * ((k >= i) + 5 - len(str(i)))
                        + s
                    )
    except Exception as e:
        copyfile(basedir + "/" + base, scopedir + "/" + base)
        raise RuntimeError(
            "Encountered uncaught exception while implementing mod changes"
        ) from e

    Path(editdir + "/" + "/".join(base.split("/")[:-1])).mkdir(
        parents=True, exist_ok=True
    )
    hashfile(scopedir + "/" + base, editdir + "/" + base + edited_suffix)


def cleanup(folder=None, echo=True):
    if not os.path.exists(folder):
        return True
    if os.path.isdir(folder):
        empty = True
        for content in os.scandir(folder):
            if cleanup(content, echo):
                empty = False
        if empty:
            os.rmdir(folder)
            return False
        return True
    if isinstance(folder, str):
        return None
    folderpath = folder.path.replace("\\", "/")
    path = folderpath[len(basedir) + 1 :]
    if os.path.isfile(scopedir + "/" + path):
        if is_edited(path):
            copyfile(folderpath, scopedir + "/" + path)
        if echo:
            alt_print(path)
        os.remove(folderpath)
        return False
    return True


def restorebase(echo=True):
    if not cleanup(basedir, echo):
        try:
            copy_tree(basedir, scopedir)
        except DistutilsFileError:
            pass


# Global Preprocessing


def thetime():
    return datetime.now().strftime("%d.%m.%Y-%I.%M%p-%S.%f")


def preplogfile():
    if do_log:
        Path(logsdir).mkdir(parents=True, exist_ok=True)
        logging.basicConfig(
            filename=logsdir + "/" + logfile_prefix + thetime() + logfile_suffix,
            level=logging.INFO,
        )
    logging.captureWarnings(do_log and not do_echo)


def update_scope(rel=".."):
    global gamedir
    gamedir = os.path.join(os.path.realpath(rel), "").replace("\\", "/")[:-1]
    global scopeparent
    scopeparent = gamedir.split("/")[-1]
    global scopedir
    scopedir = gamedir + "/" + scope


def configure_globals(condict={}, flow=True):

    global do_echo, do_log, do_input
    do_echo = util.get(condict, "echo", do_echo)
    do_log =util.get_attribute(condict, "log", do_log)
    do_input = util.get_attribute(condict, "input", do_input)

    global logsrel, logfile_prefix, logfile_suffix
    logsrel = util.get_attribute(condict, "log_folder", logsrel)
    logfile_prefix = util.get_attribute(condict, "log_prefix", logfile_prefix)
    logfile_suffix = util.get_attribute(condict, "log_suffix", logfile_suffix)

    global logsdir
    logsdir = os.path.join(os.path.realpath(logsrel), "").replace("\\", "/")
    preplogfile()

    global hashes
    hashes = util.get_attribute(condict, "hashes", hashes)

    global thisfile, localdir, localparent
    thisfile = os.path.realpath(__file__).replace("\\", "/")
    localdir = "/".join(thisfile.split("/")[:-1])
    localparent = localdir.split("/")[-2]

    global profiles, profile, folderprofile
    profiles = {}
    profiles.update(safeget(condict, "profiles", {}))
    profile = None

    folderprofile = util.get_attribute(condict, "profile", localparent)
    if profile_use_special:
        profile = util.get_attribute(condict, "profile_special", profile)
    while profile is None:
        profile = util.get_attribute(profiles, folderprofile, None)
        if profile is None:
            if not flow:
                alt_warn(MSG_MissingFolderProfile.format(configfile))
                profile = {}
                break
            folderprofile = alt_input(
                "Type the name of a profile, " + "or leave empty to cancel:\n\t> "
            )
            if not folderprofile:
                alt_warn(MSG_MissingFolderProfile.format(configfile))
                alt_exit(1)

    update_scope(safeget(profile, "game_dir_path", gamerel))

    global default_target
    default_target = profile.get("default_target", default_target)

    global scopemods, modsrel, modsabs, baserel, baseabs, editrel, editabs
    scopemods = util.get_attribute(profile, "folder_deployed", scopemods)
    modsrel = util.get_attribute(profile, "folder_mods", modsrel)
    baserel = util.get_attribute(profile, "folder_basecache", baserel)
    editrel = util.get_attribute(profile, "folder_editcache", editrel)

    global basedir
    basedir = (scopedir + "/" + baserel).replace("\\", "/")
    if not os.path.isabs(basedir):
        basedir = os.path.join(os.path.realpath(basedir), "").replace("\\", "/")[:-1]

    global editdir
    editdir = (scopedir + "/" + editrel).replace("\\", "/")
    if not os.path.isabs(editdir):
        editdir = os.path.join(os.path.realpath(editdir), "").replace("\\", "/")[:-1]

    global modsdir
    modsdir = (scopedir + "/" + modsrel).replace("\\", "/")
    if not os.path.isabs(modsdir):
        modsdir = os.path.join(os.path.realpath(modsdir), "").replace("\\", "/")[:-1]

    global deploydir
    deploydir = (scopedir + "/" + scopemods).replace("\\", "/")
    if not os.path.isabs(deploydir):
        deploydir = os.path.join(os.path.realpath(deploydir), "").replace("\\", "/")[
            :-1
        ]

    global local_in_scope, base_in_scope, edit_in_scope, mods_in_scope, deploy_in_scope, game_has_scope
    local_in_scope = (
        base_in_scope
    ) = edit_in_scope = mods_in_scope = deploy_in_scope = None

    game_has_scope = in_scope(scopedir).message == "DirInScope"
    local_in_scope = in_scope(thisfile).message == "FileInScope"

    if not game_has_scope:
        alt_warn(MSG_GameHasNoScope.format(scopedir, scopeparent, configfile))
        if flow:
            alt_exit(1)

    base_in_scope = in_scope(basedir, True).message == "DirInScope"
    edit_in_scope = in_scope(editdir, True).message == "DirInScope"
    mods_in_scope = in_scope(basedir, True).message == "DirInScope"
    deploy_in_scope = in_scope(deploydir, True).message == "DirInScope"

    if not deploy_in_scope:
        alt_warn(MSG_DeployNotInScope.format(deploydir, scopedir, configfile))
        if flow:
            alt_exit(1)

    global deploy_from_scope
    deploy_from_scope = deploydir[
        len(os.path.commonprefix([scopedir, deploydir])) + 1 :
    ]


def configsetup(predict={}, postdict={}):
    condict = cfg_framework
    if not cfg_overwrite:
        try:
            with alt_open(configfile) as f:
                condict.update(json.load(f))
        except FileNotFoundError:
            pass

    util.merge_dict(condict, predict)
    if cfg_modify:
        util.merge_dict(condict, postdict)

    if json is not None:
        with alt_open(configfile, "w") as f:
            json.dump(condict, f)

    if cfg_modify:
        alt_print("Config modification successful.")
        alt_exit(0)

    util.merge_dict(condict, postdict)
    configure_globals(condict)


# Private Globals

MSG_ConfigHelp = """
Create or configure a folder profile using:
 * config file: `profiles` in '{0}'
Or change the active folder profile using:
 * config file: `profile` in '{0}'
 * terminal option: --profile
Use and modify the special profile:
 * terminal options:
        --special
        --special-set <profile JSON>
Override the game path temporarily:
 * terminal option: --game <path to game>
"""

MSG_MissingFolderProfile = (
    """
The selected profile is not a default or configured folder profile or is configured incorrectly.
Make sure the profile is configured to the actual game directory.
Alternatively, make sure this program is in the appropriate location.
"""
    + MSG_ConfigHelp
)

MSG_GameHasNoScope = """
The folder '{0}' does not exist.
Are you sure {1} is the game's proper location?
You may need to change the path 'game_dir_path' in the profile's config.
""" + MSG_ConfigHelp.format(
    "{2}"
)

MSG_DeployNotInScope = """
Deployment folder '{0}' is not a subfolder of '{1}'.
This means deploying mods is impossible!
Configure the deployment path 'folder_deployed' to be within the content.
""" + MSG_ConfigHelp.format(
    "{2}"
)

MSG_CommandLineHelp = """
    -h --help
        print this help text
    -m --modify
        modify the config and halt
    -o --overwrite
        overwrite the config with default
    -s --special
        use special profile
    -l --log
        disable logging
    -e --echo
        disable echo
    -i --input
        disable input (input gets passed defaults)
    -c --config <relative file path>
        choose config file
    -H --hashes <space separated hash names>
        hashes used to compare files in edit cache (ie, "md5 sha1")
    -g --game <relative folder path>
        temporarily use a different game directory
    -p --profile <profile name>
        use a particular folder profile
    -S --special-set <profile JSON>
        map JSON to the special profile
        
"""

default_target = []
default_priority = 100

modfile = "modfile.txt"
modfile_mlcom_start = "-:"
modfile_mlcom_end = ":-"
modfile_comment = "::"
modfile_linebreak = ";"
modfile_delimiter = ","

modfile_keywords = {
    "to"            : ("To",),
    "load"          : ("Load",),
    "priority"      : ("Priority",),
    "include"       : ("Include",),
    "deploy"        : ("Deploy",)
}

modfile_payloads = OrderedDict()

modfile_payloads["replace"]         = (lambda s,d: file_replace(s,d[0]),("Replace",),1)
modfile_payloads["package_copy"]    = (lambda s,d: package_copy(s,d[0]),("Package","Copy"),1)
modfile_payloads["package_patch"]   = (lambda s,d: package_patch(s,d[0]),("Package","Patch"),1)
modfile_payloads["import"]          = (lambda s,d: lua_import(s,d[0]),("Import",),1)
modfile_payloads["import_top"]      = (lambda s,d: lua_import_top(s,d[0]),("Top","Import"),1)
modfile_payloads["sjson"]           = (lambda s,d: sjson_merge(s,d[0]),("SJSON",),1,sjson,"SJSON")
modfile_payloads["xml"]             = (lambda s,d: sggmi_xml.merge(s,d[0]),sggmi_xml.KEYWORD,1)

scope = "Content"
importscope = "Scripts"
localsources = {"SGGMI"}

profile_template = {
    "default_target": None,
    "game_dir_path": None,
    "folder_deployed": None,
    "folder_mods": None,
    "folder_basecache": None,
    "folder_editcache": None,
}

default_profiles = {
    "Hades": {
        "default_target": ["Scripts/RoomManager.lua"],
    },
    "Pyre": {
        "default_target": ["Scripts/Campaign.lua", "Scripts/MPScripts.lua"],
    },
    "Transistor": {
        "default_target": ["Scripts/AllCampaignScripts.txt"],
    },
    "Bastion": {},
}

for k, v in default_profiles.items():
    default_profiles[k] = util.merge_dict(profile_template.copy(), v, modify_original=False)

cfg_framework = {
    "echo": True,
    "input": True,
    "log": True,
    "hashes": hashes,
    "profile": None,
    "profile_special": profile_template,
    "profiles": default_profiles,
    "log_folder": None,
    "log_prefix": None,
    "log_suffix": None,
}

# Main Process


def start(*args, **kwargs):

    configsetup(kwargs.get("predict", {}), kwargs.get("postdict", {}))

    global codes
    codes = defaultdict(list)
    global todeploy
    todeploy = {}

    # remove anything in the base cache that is not in the edit cache
    alt_print("Cleaning edits... (if there are issues validate/reinstall files)")
    restorebase()

    # remove the edit cache and base cache from the last run
    def onerror(func, path, exc_info):
        if not os.access(path, os.W_OK):
            os.chmod(path, stat.S_IWUSR)
            func(path)
        else:
            raise

    rmtree(editdir, onerror)
    Path(editdir).mkdir(parents=True, exist_ok=True)
    rmtree(basedir, onerror)
    Path(basedir).mkdir(parents=True, exist_ok=True)
    Path(modsdir).mkdir(parents=True, exist_ok=True)
    Path(deploydir).mkdir(parents=True, exist_ok=True)

    alt_print("\nReading mod files...")
    for mod in os.scandir(modsdir):
        modfile_load(mod.path.replace("\\", "/") + "/" + modfile)

    deploy_mods()

    alt_print("\nModified files for " + folderprofile + " mods:")
    for base, mods in codes.items():
        sort_mods(base, mods)
        make_base_edits(base, mods)

    bs = len(codes)
    ms = sum(map(len, codes.values()))

    alt_print(
        "\n"
        + str(bs)
        + " file"
        + ("s are", " is")[bs == 1]
        + " modified by"
        + " a total of "
        + str(ms)
        + " mod file"
        + "s" * (ms != 1)
        + "."
    )


def main_action(*args, **kwargs):
    try:
        start(*args, **kwargs)
    except Exception as e:
        alt_print("There was a critical error, now attempting to display the error")
        alt_print(
            "(if this doesn't work, try again in a terminal"
            + " which doesn't close, or check the log files)"
        )
        logging.getLogger("MainExceptions").exception(e)
        alt_input("Press any key to see the error...")
        raise RuntimeError("Encountered uncaught exception during program") from e
    alt_input("Press any key to end program...")


def main(*args, **kwargs):
    predict = {}
    postdict = {}

    opts, _ = getopt(
        args,
        "hmsoleic:g:p:S:H:",
        [
            "config=",
            "log_folder=",
            "echo",
            "input",
            "special",
            "log",
            "log-prefix=",
            "log-suffix=",
            "profile=,help",
            "special-set=",
            "game=",
            "modify",
            "overwrite",
            "--hash=",
        ],
    )

    global cfg_modify, cfg_overwrite, profile_use_special, configfile, gamerel

    for k, v in opts:
        if k in {"-h", "--help"}:
            print(MSG_CommandLineHelp)
            return
        elif k in {"-m", "--modify"}:
            cfg_modify = True
        elif k in {"-o", "--overwrite"}:
            cfg_overwrite = True
        elif k in {"-s", "--special"}:
            profile_use_special = True
        elif k in {"-l", "--log"}:
            postdict["log"]
        elif k in {"-e", "--echo"}:
            postdict["echo"] = False
        elif k in {"-i", "--input"}:
            postdict["input"] = False
        elif k in {"-c", "--config"}:
            configfile = v
        elif k in {"-g", "--game"}:
            gamerel = v
        elif k in {"-p", "--profile"}:
            postdict["profile"] = v
        elif k in {"-p", "--profile"}:
            postdict["hashes"] = v.split(" ")
        elif k in {"-S", "--special-set"}:
            predict.setdefault("profile_special", {})
            predict["profile_special"] = json.loads(v)

    main_action(*args, predict=predict, postdict=postdict)


do_log = True
cfg_modify = False
cfg_overwrite = False
profile_use_special = False
gamerel = ".."

if __name__ == "__main__":
    do_echo = True
    do_input = True
    main(*sys.argv[1:])
else:
    do_echo = False
    do_input = False

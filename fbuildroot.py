from itertools import chain
from optparse import make_option

import fbuild
import fbuild.db
from fbuild.functools import call
from fbuild.path import Path
from fbuild.record import Record

from fbuild.builders import platform
guess_platform = platform.guess_platform

def static_obj_suffix(ctx, platform=None):
    platform = platform or guess_platform(ctx)
    if 'windows' in platform:
        return '_static.obj'
    else:
        return '_static.o'

def shared_obj_suffix(ctx, platform=None):
    platform = platform or guess_platform(ctx)
    if 'windows' in platform:
        return '_dynamic.obj'
    else:
        return '_dynamic.o'

platform.static_obj_suffix = static_obj_suffix
platform.shared_obj_suffix = shared_obj_suffix

import buildsystem
from buildsystem.config import config_call
from buildsystem.version import flx_version

# HACK
import os, sys

import time
now = time.time()
gmtime = time.gmtime(now)

from os.path import join
import fnmatch

# ------------------------------------------------------------------------------

def pre_options(parser):
    group = parser.add_option_group('config options')
    group.add_options((
        make_option('--prefix',
            default='/usr/local',
            help='specify the install location (default /usr/local)'),
        make_option('--bindir',
            default=None,
            help='specify the binary install location (default $PREFIX/bin)'),
        make_option('--libdir',
            default=None,
            help='specify the library install location (default $PREFIX/lib)'),
        make_option('-I', '--include',
            dest='includes',
            default=[],
            action='append',
            help='add this path to the c header search path for all phases'),
        make_option('-L', '--library-path',
            dest='libpaths',
            default=[],
            action='append',
            help='add this path to the c library search path for all phases'),
        make_option('--c-flag',
            dest='c_flags',
            default=[],
            action='append',
            help='add this flag to the c compiler'),
        make_option('--cxx-flag',
            dest='cxx_flags',
            default=[],
            action='append',
            help='add this flag to the c++ compiler'),
        make_option('-g', '--debug',
            default=False,
            action='store_true',
            help='enable debugging for all phases'),
        make_option('--skip-tests',
            default=False,
            action='store_true',
            help='skip running tests'),
    ))

    group = parser.add_option_group('build phase options')
    group.add_options((
        make_option('--build-platform',
            help='specify the build phase platform'),
        make_option('--build-cc',
            help='specify the build phase c compiler'),
        make_option('--build-cxx',
            help='specify the build phase c++ compiler'),
        make_option('--build-include',
            dest='build_includes',
            default=[],
            action='append',
            help='add this path to the c header search path for the build ' \
                    'phase'),
        make_option('--build-library-path',
            dest='build_libpaths',
            default=[],
            action='append',
            help='add this path to the c library search path for the build ' \
                    'phase'),
        make_option('--build-c-flag',
            dest='build_c_flags',
            default=[],
            action='append',
            help='add this flag to the c compiler for the build phase'),
        make_option('--build-cxx-flag',
            dest='build_cxx_flags',
            default=[],
            action='append',
            help='add this flag to the c++ compiler for the build phase'),
        make_option('--build-c-debug',
            default=False,
            action='store_true',
            help='turn on c/c++ build phase debugging'),
    ))

    group = parser.add_option_group('host phase options')
    group.add_options((
        make_option('--host-platform',
            help='specify the host phase platform'),
        make_option('--host-cc',
            help='specify the host phase c compiler'),
        make_option('--host-cxx',
            help='specify the host phase c++ compiler'),
        make_option('--host-include',
            dest='host_includes',
            default=[],
            action='append',
            help='Add this path to the c header search path for the host ' \
                    'phase'),
        make_option('--host-library-path',
            dest='host_libpaths',
            default=[],
            action='append',
            help='Add this path to the c library search path for the host ' \
                    'phase'),
        make_option('--host-c-flag',
            dest='host_c_flags',
            default=[],
            action='append',
            help='Add this flag to the c compiler for the host phase'),
        make_option('--host-cxx-flag',
            dest='host_cxx_flags',
            default=[],
            action='append',
            help='add this flag to the c++ compiler for the host phase'),
        make_option('--host-c-debug',
            default=False,
            action='store_true',
            help='turn on c/c++ host phase debugging'),
        make_option('--host-ocaml-debug',
            default=False,
            action='store_true',
            help='turn on ocaml debugging'),
        make_option('--host-ocamlc',
            help='specify the ocaml bytecode compiler'),
        make_option('--host-ocamlopt',
            help='specify the ocaml native compiler'),
        make_option('--host-ocamllex',
            help='specify the ocaml lexer'),
        make_option('--host-llvm-config',
            help='specify the llvm-config script'),
    ))

    group = parser.add_option_group('target phase options')
    group.add_options((
        make_option('--target-platform',
            help='specify the target phase platform'),
        make_option('--target-cc',
            help='specify the target phase c compiler'),
        make_option('--target-cxx',
            help='specify the target phase c++ compiler'),
        make_option('--target-include',
            dest='target_includes',
            default=[],
            action='append',
            help='add this path to the c header search path for the target ' \
                    'phase'),
        make_option('--target-library-path',
            dest='target_libpaths',
            default=[],
            action='append',
            help='add this path to the c library search path for the target ' \
                    'phase'),
        make_option('--target-c-debug',
            default=False,
            action='store_true',
            help='turn on c/c++ target phase debugging'),
        make_option('--target-c-flag',
            dest='target_c_flags',
            default=[],
            action='append',
            help='add this flag to the c compiler for the target phase'),
        make_option('--targe-cxx-flag',
            dest='target_cxx_flags',
            default=[],
            action='append',
            help='add this flag to the c++ compiler for the target phase'),
        make_option('--target-sdl-config',
            help='specify the sdl-config script'),
    ))

def post_options(options, args):
    options.prefix = Path(options.prefix)
    options.bindir = Path(
        options.prefix / 'bin' if options.bindir is None else options.bindir)
    options.libdir = Path(
        options.prefix / 'lib' if options.libdir is None else options.libdir)

    if options.debug:
        options.buildroot = Path(options.buildroot, 'debug')
    else:
        options.buildroot = Path(options.buildroot, 'release')

    return options, args

# ------------------------------------------------------------------------------

def make_c_builder(ctx, *args, includes=[], libpaths=[], flags=[], **kwargs):
    flags = list(chain(ctx.options.c_flags, flags))

    kwargs['platform_options'] = [
        # GRRR .. for clang
        ({'darwin'},
            {'warnings': ['all', 'fatal-errors',
                'no-constant-logical-operand',
                'no-array-bounds',
                ],
            'flags': ['-fno-common','-fvisibility=hidden'] + flags,
            'optimize_flags': ['-fomit-frame-pointer']}),
        ({'posix'},
            {'warnings': ['all', 'fatal-errors'],
            'flags': ['-std=gnu89', '-fno-common', '-fvisibility=hidden', '-fno-strict-aliasing'] + flags,
            'optimize_flags': ['-fomit-frame-pointer']}),
        ({'windows'}, {
            'link_flags' : ['/DEBUG'],
            'flags': ['/GR', '/MDd', '/EHs', '/Zi', '/wd4291'] + flags,
            'optimize_flags': ['/Ox']}),
    ]
    kwargs['includes'] = list(chain(ctx.options.includes, includes))
    kwargs['libpaths'] = list(chain(ctx.options.libpaths, libpaths))

    return Record(
        static=call('fbuild.builders.c.guess_static', ctx, *args, **kwargs),
        shared=call('fbuild.builders.c.guess_shared', ctx, *args, **kwargs))

def make_cxx_builder(ctx, *args, includes=[], libpaths=[], flags=[], **kwargs):
    flags = list(chain(ctx.options.cxx_flags, flags))

    kwargs['platform_options'] = [
        # GRRR .. for clang++
        ({'darwin'}, {
            'warnings': ['fatal-errors',
                'no-invalid-offsetof',
                'no-logical-op-parentheses',
                'no-bitwise-op-parentheses',
                'no-parentheses-equality',
                'no-parentheses',
                'no-return-stack-address',
                'no-tautological-compare',
                'no-return-type-c-linkage',
                'no-unused-variable',
                'no-unused-function',
                'no-c++11-narrowing',
                'no-missing-braces',
                'no-return-type-c-linkage',
                ],
            'flags': [
                '-w', '-fno-common', '-fno-strict-aliasing',
                '-fvisibility=hidden', '-std=c++11'] + flags,
            'optimize_flags': ['-fomit-frame-pointer']}),
        #({'cygwin'}, {
        #    'warnings': ['fatal-errors', 'no-invalid-offsetof','no-parentheses'],
        #    'flags': ['-std=gnu++11', '-w',
        #     '-fno-common', '-fvisibility=hidden', '-fno-strict-aliasing'] + flags,
        #    'optimize_flags': ['-fomit-frame-pointer']}),
        ({'posix'}, {
            'warnings': ['fatal-errors', 'no-invalid-offsetof','no-parentheses'],
            'flags': ['-std=gnu++11', '-D_POSIX', '-w',
               '-fno-common', '-fvisibility=hidden', '-fno-strict-aliasing'] + flags,
            'optimize_flags': ['-fomit-frame-pointer']}),
        ({'windows'}, {
            'link_flags' : ['/DEBUG'],
            'flags': ['/GR', '/MDd', '/EHs', '/Zi', '/wd4291', '/wd4190'] + flags,
            'optimize_flags': ['/Ox']}),
    ]
    kwargs['includes'] = list(chain(ctx.options.includes, includes))
    kwargs['libpaths'] = list(chain(ctx.options.libpaths, libpaths))

    return Record(
        static=call('fbuild.builders.cxx.guess_static', ctx, *args, **kwargs),
        shared=call('fbuild.builders.cxx.guess_shared', ctx, *args, **kwargs))

def config_build(ctx):
    ctx.logger.log('configuring build phase', color='cyan')

    platform = call('fbuild.builders.platform.guess_platform', ctx,
        ctx.options.build_platform)
    return Record(
        ctx=ctx,
        platform=platform,
        c=make_c_builder(ctx, exe=ctx.options.build_cc,
            platform=platform,
            debug=ctx.options.debug or ctx.options.build_c_debug,
            optimize=not (ctx.options.debug or ctx.options.build_c_debug),
            includes=ctx.options.build_includes,
            libpaths=ctx.options.build_libpaths,
            flags=ctx.options.build_c_flags),
        cxx=make_cxx_builder(ctx, exe=ctx.options.build_cxx,
            platform=platform,
            debug=ctx.options.debug or ctx.options.build_c_debug,
            optimize=not (ctx.options.debug or ctx.options.build_c_debug),
            includes=ctx.options.build_includes,
            libpaths=ctx.options.build_libpaths,
            flags=ctx.options.build_cxx_flags))

def config_host(ctx, build):
    ctx.logger.log('configuring host phase', color='cyan')

    platform = call('fbuild.builders.platform.guess_platform', ctx,
        ctx.options.build_platform)

    if platform == build.platform:
        ctx.logger.log("using build's c and cxx compiler", color='cyan')
        phase = build
    else:
        phase = Record(
            ctx=ctx,
            platform=platform,
            c=make_c_builder(ctx, exe=fbuild.builders.host_cc,
                platform=platform,
                debug=ctx.options.debug or ctx.options.host_c_debug,
                optimize=not (ctx.options.debug or ctx.options.host_c_debug),
                includes=ctx.options.host_includes,
                libpaths=ctx.options.host_libpaths,
                flags=ctx.options.host_c_flags),
            cxx=make_cxx_builder(ctx, exe=fbuild.builders.host_cxx,
                platform=platform,
                debug=ctx.options.debug or ctx.options.host_c_debug,
                optimize=not (ctx.options.debug or ctx.options.host_c_debug),
                includes=ctx.options.host_includes,
                libpaths=ctx.options.host_libpaths,
                flags=ctx.options.host_cxx_flags))

    phase.ocaml = call('fbuild.builders.ocaml.Ocaml', ctx,
        debug=ctx.options.debug or ctx.options.host_ocaml_debug,
        ocamlc=ctx.options.host_ocamlc,
        ocamlopt=ctx.options.host_ocamlopt,
        flags=['-w', 'yzex', '-warn-error', 'FPSU'],
        linker=phase.c.static.lib_linker,
        requires_at_least_version=(3, 11))

    phase.ocamllex = call('fbuild.builders.ocaml.Ocamllex', ctx,
        ctx.options.host_ocamllex)

    # we prefer the native ocaml as it's much faster
    if hasattr(phase.ocaml, 'ocamlopt'):
        phase.ocaml = phase.ocaml.ocamlopt
    else:
        phase.ocaml = phase.ocaml.ocamlc

    # We optionally support llvm
    try:
        llvm_config = call('fbuild.builders.llvm.LlvmConfig', ctx,
            ctx.options.host_llvm_config,
            requires_at_least_version=(2, 7))
    except fbuild.ConfigFailed:
        phase.llvm_config = None
    else:
        if llvm_config.ocaml_libdir().exists():
            #phase.llvm_config = llvm_config
            phase.llvm_config = None
        else:
            phase.llvm_config = None

    return phase

def config_target(ctx, host):
    ctx.logger.log('configuring target phase', color='cyan')

    platform = call('fbuild.builders.platform.guess_platform', ctx,
        ctx.options.target_platform)

    if platform == host.platform:
        ctx.logger.log("using host's c and cxx compiler", color='cyan')
        phase = host
    else:
        phase = Record(
            ctx=ctx,
            platform=platform,
            c=make_c_builder(ctx, exe=ctx.options.target_cc,
                platform=platform,
                debug=ctx.options.debug or ctx.options.target_c_debug,
                optimize=not (ctx.options.debug or ctx.options.target_c_debug),
                includes=ctx.options.target_includes,
                libpaths=ctx.options.target_libpaths,
                flags=ctx.options.target_c_flags),
            cxx=make_cxx_builder(ctx, exe=ctx.options.target_cxx,
                platform=platform,
                debug=ctx.options.debug or ctx.options.target_c_debug,
                optimize=not(ctx.options.debug or ctx.options.target_c_debug),
                includes=ctx.options.target_includes,
                libpaths=ctx.options.target_libpaths,
                flags=ctx.options.target_cxx_flags))

    # We optionally support sdl
    try:
        phase.sdl_config = call('fbuild.builders.sdl.SDLConfig', ctx,
            ctx.options.target_sdl_config,
            requires_at_least_version=(1, 3))
    except (fbuild.ConfigFailed,OSError):
        phase.sdl_config = None

    return phase

# ------------------------------------------------------------------------------

@fbuild.db.caches
def prefix(ctx):
    prefix = Path(ctx.options.prefix)
    ctx.logger.check('install prefix', prefix, color='cyan')

    return prefix

@fbuild.db.caches
def src_dir(ctx):
    return Path(__file__).parent

# ------------------------------------------------------------------------------

# SHOULD USE REGEXP
def hack_toolchain_name(s):
  if s in ["gcc-5","gcc-6","gcc-7"]: return "gcc"
  if s in ["clang","gcc"]: return s
  return s

def tangle_packages(package_dir, odir):
    # import the processing logic from flx_iscr
    sys.path.append("src/tools/")
    import flx_iscr

    quiet = True
    flx_iscr.process_dir(package_dir, odir, quiet)

def find_grammar(build_dir):
    sys.path.append("src/tools/")
    import flx_find_grammar_files

    flx_find_grammar_files.run(build_dir)

def write_script(buildroot,version):
    Path("installscript").makedirs()
    f = open (Path("installscript") / "posixinstall.sh","w")
    f.write(r"rm -rfd /usr/local/lib/felix/felix-"+version+r""+"\n")
    f.write(r"mkdir -p /usr/local/lib/felix/felix-"+version+r"/share"+"\n")
    f.write(r"mkdir -p /usr/local/lib/felix/felix-"+version+r"/host"+"\n")
    f.write(r"cp -r build/release/share/* /usr/local/lib/felix/felix-"+version+r"/share"+"\n")
    f.write(r"cp -r build/release/host/* /usr/local/lib/felix/felix-"+version+r"/host"+"\n")
    f.close()

    f = open (Path("installscript") / "win32install.bat","w")
    f.write(r"@echo off")
    f.write(r"mkdir c:\usr\local\lib\felix\felix-"+version+r"\crap"+"\n")
    f.write(r"rmdir /S /Q c:\usr\local\lib\felix\felix-"+version+r""+"\n")
    f.write(r"mkdir c:\usr\local\lib\felix\felix-"+version+r"\share"+"\n")
    f.write(r"mkdir c:\usr\local\lib\felix\felix-"+version+r"\host"+"\n")
    f.write(r"xcopy /E build\release\share\* c:\usr\local\lib\felix\felix-"+version+r"\share"+"\n")
    f.write(r"xcopy /E build\release\host\* c:\usr\local\lib\felix\felix-"+version+r"\host"+"\n")
    f.close()

    f = open (Path("installscript") / "linuxsetup.sh","w")
    f.write(r"export PATH=/usr/local/lib/felix/felix-"+version+r"/host/bin:$PATH"+"\n")
    f.write(r"export LD_LIBRARY_PATH=/usr/local/lib/felix/felix-"+version+r"/host/lib/rtl:$LD_LIBRARY_PATH"+"\n")
    f.close()

    f = open (Path("installscript") / "osxsetup.sh","w")
    f.write(r"export PATH=/usr/local/lib/felix/felix-"+version+r"/host/bin:$PATH"+"\n")
    f.write(r"export DYLD_LIBRARY_PATH=/usr/local/lib/felix/felix-"+version+r"/host/lib/rtl:$DYLD_LIBRARY_PATH"+"\n")
    f.close()

    f = open (Path("installscript") / "win32setup.bat","w")
    f.write(r"@echo off"+"\n")
    f.write(r"set PATH=C:\usr\local\lib\felix\felix-"+version+r"\host\bin;C:\usr\local\lib\felix\felix-"+version+r"\host\lib\rtl;%PATH%"+"\n")
    f.close()

    f = open("VERSION","w")
    f.write(flx_version+"\n")
    f.close()

    short_time = time.strftime("%a %d %b %Y",gmtime)
    (buildroot/"src"/"compiler"/"flx_version_hook").makedirs()
    f = open (buildroot/"src"/"compiler"/"flx_version_hook"/"flx_version_hook.ml","w")
    f.write("open Flx_version\n")
    f.write("let version_data: version_data_t =\n")
    f.write("{\n")
    f.write('  version_string = "%s";' % flx_version+"\n")
    f.write('  build_time_float = %s;' % now+"\n")
    f.write('  build_time = "%s";' % time.ctime(now)+"\n")
    f.write("}\n")
    f.write(";;\n")
    f.write("let set_version () =\n")
    f.write("  Flx_version.version_data := version_data\n")
    f.write(";;\n")

    (buildroot/"share"/"lib"/"std").makedirs()
    f = open(buildroot/"share"/"lib"/"std"/"version.flx","w")
    f.write("// GENERATED DURING BUILD (for version number)\n")
    f.write("class Version\n")
    f.write("{\n")
    f.write('  const felix_version : string = \'::std::string("'+flx_version+'")\';\n')
    f.write("}\n")
    f.close()

def set_version(buildroot):
  print("FELIX VERSION " + flx_version)
  write_script(buildroot,flx_version)

@fbuild.db.caches
def configure(ctx):
    """Configure Felix."""

    build = config_build(ctx)
    host = config_host(ctx, build)
    target = config_target(ctx, host)

    # Make sure the config directories exist.
    #(ctx.buildroot / 'host/config').makedirs()

    # copy the config directory for initial config
    # this will be overwritten by subsequent steps if
    # necessary
    #
    buildsystem.copy_to(ctx, ctx.buildroot/'host/config', Path('src/config/*.fpc').glob())
    # most of these ones are actually platform independent
    # just do the windows EXTERN to dllexport mapping
    # which is controlled by compile time switches anyhow
    # should probably move these out of config directory
    # they're put in config in case there really are any
    # platform mods.
    buildsystem.copy_to(ctx, ctx.buildroot/'host/lib/rtl',
        Path('src/config/target/*.hpp').glob())
    buildsystem.copy_to(ctx, ctx.buildroot/'host/lib/rtl',
        Path('src/config/target/*.h').glob())

    types = config_call('fbuild.config.c.c99.types',
        target.platform, target.c.static)


    # this is a hack: assume we're running on Unix.
    # later when Erick figures out how to fix this
    # we'd copy the win32 subdirectory entries instead
    if "posix" in target.platform:
        print("COPYING POSIX RESOURCE DATABASE")
        buildsystem.copy_to(ctx,
            ctx.buildroot / 'host/config', Path('src/config/unix/*.fpc').glob())
        if types.voidp.size == 4:
            print("32 bit Unix")
            buildsystem.copy_to(ctx,
              ctx.buildroot / 'host/config', Path('src/config/unix/unix32/*.fpc').glob())
        else:
            print("64 bit Unix")
            buildsystem.copy_to(ctx,
            ctx.buildroot / 'host/config', Path('src/config/unix/unix64/*.fpc').glob())

    if "linux" in target.platform:
        print("COPYING LINUX RESOURCE DATABASE")
        buildsystem.copy_to(ctx,
            ctx.buildroot / 'host/config', Path('src/config/linux/*.fpc').glob())


    # enable this on win32 **instead** of the above to copy fpc files
    if "windows" in target.platform:
        print("COPYING WIN32 RESOURCE DATABASE")
        buildsystem.copy_to(ctx,
            ctx.buildroot / 'host/config', Path('src/config/win32/*.fpc').glob())

    # enable this on solaris to clobber any fpc files
    # where the generic unix ones are inadequate
    #buildsystem.copy_to(ctx,
    #    ctx.buildroot / 'config', Path('src/config/solaris/*.fpc').glob())

    # enable this on osx to clobber any fpc files
    # where the generic unix ones are inadequate
    if 'macosx' in target.platform:
        print("COPYING MACOSX RESOURCE DATABASE")
        buildsystem.copy_to(ctx,
            ctx.buildroot / 'host/config', Path('src/config/macosx/*.fpc').glob())

    if 'cygwin' in target.platform:
        print("COPYING CYWGIN (POSIX) RESOURCE DATABASE")
        buildsystem.copy_to(ctx,
            ctx.buildroot / 'host/config', Path('src/config/cygwin/*.fpc').glob())

    if 'msys' in target.platform:
        print("COPYING MSYS RESOURCE DATABASE")
        buildsystem.copy_to(ctx,
            ctx.buildroot / 'host/config', Path('src/config/msys/*.fpc').glob())


    if 'solaris' in target.platform:
        print("COPYING SOLARIS RESOURCE DATABASE")
        buildsystem.copy_to(ctx,
            ctx.buildroot / 'host/config', Path('src/config/solaris/*.fpc').glob())


    # extract the configuration
    iscr = call('buildsystem.iscr.Iscr', ctx)

    # convert the config into something iscr can use
    call('buildsystem.iscr.config_iscr_config', ctx, build, host, target)

    # re-extract packages if any of them changed
    ctx.scheduler.map(iscr, (src_dir(ctx)/'lpsrc/*.pak').glob())

    # overwrite or add *.fpc files to the config directory
    call('buildsystem.post_config.copy_user_fpcs', ctx)

    # set the toolchain
    dst = ctx.buildroot / 'host/config/toolchain.fpc'
    if 'macosx' in target.platform:
        toolchain = "toolchain_"+hack_toolchain_name(str(target.c.static))+"_osx"
    elif "windows" in target.platform:
        toolchain= "toolchain_msvc_win32"
    else:
        toolchain = "toolchain_"+hack_toolchain_name(str(target.c.static))+"_linux"
    print("**********************************************")
    print("SETTING TOOLCHAIN " + toolchain)
    print("**********************************************")
    f = open(dst,"w")
    f.write ("toolchain: "+toolchain+"\n")
    f.close()

    # make Felix representation of whole build config
    call('buildsystem.show_build_config.build',ctx)

    return Record(build=build, host=host, target=target), iscr

# ------------------------------------------------------------------------------

def build(ctx):
    """Compile Felix."""

    set_version(ctx.buildroot)

    print("[fbuild] RUNNING PACKAGE MANAGER")
    tangle_packages(Path("src")/"packages", ctx.buildroot)

    print("[fbuild] CONFIGURING FELIX")
    # configure the phases
    phases, iscr = configure(ctx)

    # --------------------------------------------------------------------------
    # Compile the compiler.

    print("[fbuild] [ocaml] COMPILING COMPILER")
    compilers = call('buildsystem.flx_compiler.build_flx_drivers', ctx,
        phases.host)
    print("[fbuild] COPYING REPOSITORY from current directory ..")
    buildsystem.copy_dir_to(ctx, ctx.buildroot/'share'/'src', 'src',
        pattern='*')

    print("[fbuild] INSTALLING FELIX LIBRARIES")
    buildsystem.copy_dir_to(ctx, ctx.buildroot/'share'/'lib',
        ctx.buildroot/'share'/'src'/'lib', pattern='*')

    print("[fbuild] RUNNING SYNTAX EXTRACTOR")
    find_grammar(ctx.buildroot);


    # --------------------------------------------------------------------------
    # Compile the runtime dependencies.

    print("[fbuild] [C++] COMPILING RUN TIME LIBRARY")
    call('buildsystem.judy.build_runtime', phases.target)
    call('buildsystem.re2.build_runtime', phases.target)

    # --------------------------------------------------------------------------
    # Build the standard library.

    print("[fbuild] [Felix] BUILDING STANDARD LIBRARY")
    # copy files into the library
    for module in ( 'flx_stdlib',):
        call('buildsystem.' + module + '.build_flx', phases.target)

    # --------------------------------------------------------------------------
    # Compile the runtime drivers.

    print("[fbuild] [C++] COMPILING DRIVERS")
    drivers = call('buildsystem.flx_drivers.build', phases.target)

    # --------------------------------------------------------------------------
    # Compile the builder.

    print("[fbuild] [Felix] COMPILING TOOLS")
    flx_builder = call('buildsystem.flx.build', ctx,
        compilers.flxg, phases.target.cxx.static, drivers)

    flx_pkgconfig = call('buildsystem.flx.build_flx_pkgconfig',
        phases.target, flx_builder)
    flx = call('buildsystem.flx.build_flx', phases.target, flx_builder)

    # --------------------------------------------------------------------------
    # now, try building a file

    print("[fbuild] [Felix] TEST BUILD")
    felix = call('fbuild.builders.felix.Felix', ctx,
        exe=ctx.buildroot / 'host/bin/bootflx',
        debug=ctx.options.debug,
        flags=['--test=' + ctx.buildroot])

    print("[fbuild] [Felix] BUILDING PLUGINS")
    call('buildsystem.plugins.build', phases.target, felix)

    print("[fbuild] BUILD COMPLETE")
    return phases, iscr, felix


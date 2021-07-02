import atexit
import re
import json
import os
import sys
from traitlets import Dict, Unicode

from metakernel import MetaKernel, ProcessMetaKernel, REPLWrapper, u, MetaKernelApp
from metakernel.pexpect import which

STDIN_PROMPT = '@@@---->'

NGN_K_DIR = os.environ.get('NGN_K_DIR')

def get_kernel_json():
    """Get the kernel json for the kernel.
    """
    here = os.path.dirname(__file__)
    default_json_file = os.path.join(here, 'kernel.json')
    json_file = os.environ.get('K_KERNEL_JSON', default_json_file)
    with open(json_file) as fid:
        data = json.load(fid)
    data['argv'][0] = sys.executable
    return data

class KKernel(ProcessMetaKernel):
    app_name = 'k_kernel'
    implementation = 'K Kernel'
    language = 'k'

    kernel_json = Dict(get_kernel_json()).tag(config=True)
    cli_options = Unicode('').tag(config=True)

    _k_engine = None

    @property
    def banner(self):
        msg = 'K Kernel running ngn/k'
        return msg

    @property
    def k_engine(self):
        if self._k_engine:
            return self._k_engine
        self._k_engine = KEngine(error_handler=self.Error,
                                 stream_handler=self.Print,
                                 cli_options=self.cli_options,
                                 logger=self.log)
        return self._k_engine

    def makeWrapper(self):
        return self.k_engine.repl

    def do_execute_direct(self, code, silent=False):
        if code.strip() == r'\\':
            self._k_engine = None
            self.do_shutdown(True)
            return
        return ProcessMetaKernel.do_execute_direct(self, code, silent=silent)

class KEngine(object):

    def __init__(self, error_handler=None, stream_handler=None,
                 line_handler=None,
                 stdin_handler=None,
                 cli_options='', logger=None):
        if not logger:
            logger = logging.getLogger(__name__)
            logging.basicConfig()
        self.logger = logger
        self.cli_options = cli_options
        self.repl = self._create_repl()
        self.error_handler = error_handler
        self.stream_handler = stream_handler
        self.stdin_handler = stdin_handler or sys.stdin
        self.line_handler = line_handler
        atexit.register(self._cleanup)


    def eval(self, code, timeout=None, silent=False):
        """Evaluate code using the engine.
        """
        stream_handler = None if silent else self.stream_handler
        line_handler = None if silent else self.line_handler

        if self.logger:
            self.logger.debug('K eval:')
            self.logger.debug(code)
        try:
            resp = self.repl.run_command(code.rstrip(),
                                         timeout=timeout,
                                         stream_handler=stream_handler,
                                         line_handler=line_handler,
                                         stdin_handler=self.stdin_handler)
            resp = resp.replace(STDIN_PROMPT, '')
            if self.logger and resp:
                self.logger.debug(resp)
            return resp
        except KeyboardInterrupt:
            return self._interrupt(silent=True)
        except Exception as e:
            if self.error_handler:
                self.error_handler(e)
            else:
                raise e

    def _create_repl(self):
        cmd = f'{NGN_K_DIR}/k {NGN_K_DIR}/repl.k'

        repl = REPLWrapper(cmd, " ", f'repl.prompt:"{STDIN_PROMPT}"',
                           new_prompt_regex=STDIN_PROMPT,
                           force_prompt_on_continuation=True)
        repl.child.delaybeforesend = None
        return repl

    def _interrupt(self, continuation=False, silent=False):
        return REPLWrapper.interrupt(self.repl, continuation=continuation)

    def _cleanup(self):
        """Clean up resources used by the session.
        """
        try:
            self.repl.terminate()
        except Exception as e:
            self.logger.debug(str(e))

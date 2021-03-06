# The MIT License (MIT)

# Copyright (c) 2016 Chris Webb

# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

from sublime import save_settings, load_settings, status_message, ok_cancel_dialog, Region, active_window, set_timeout
from sublime_plugin import TextCommand, WindowCommand, EventListener
from collections import MutableMapping 
from abc import ABCMeta
from threading import Thread, Lock
from time import time
from subprocess import Popen, PIPE, STDOUT
from os import environ
from os.path import isfile, expanduser, split
from traceback import format_exc

def set_status(msg):
    set_timeout(lambda:status_message(msg))

class PsqlBaseTextCommand(TextCommand, metaclass=ABCMeta):  

    __settings = None
    __window = None
    @property
    def window(self):
        if self.__window is None:
            self.__window = self.view.window()
            if self.__window is None:
                self.__window = active_window()
        return self.__window

    @property
    def settings(self):
        if self.__settings is None:
            self.__settings = PsqlSettings(window=self.window)
        return self.__settings

    @settings.setter
    def function(self, *args, **kwargs):
        self.__settings.update(dict(*args, **kwargs))

class PsqlBaseWindowCommand(WindowCommand, metaclass=ABCMeta):  

    __settings = None
    @property
    def settings(self):
        if self.__settings is None:
            self.__settings = PsqlSettings(window=self.window)
        return self.__settings

    @settings.setter
    def function(self, *args, **kwargs):
        self.__settings.update(dict(*args, **kwargs))

class PsqlEventListener(EventListener):  
    def post_window_command(window, command_name, args):
        if command_name == 'close_window':
            PsqlSettings.window_closed(window)



class PsqlSettings(MutableMapping):
    __settings_name = 'PostgreSQL Developer Tools.sublime-settings'
    __settings = None
    __windows = {}

    __postgres_variables = { 
        'host':'PGHOST', 'hostaddr':'PGHOSTADDR', 'port':'PGPORT', 
        'database':'PGDATABASE', 'user':'PGUSER', 'password':'PGPASSWORD',
        'passfile':'PGPASSFILE', 'service':'PGSERVICE', 'servicefile':'PGSERVICEFILE',
        'kerberos_realm':'PGREALM', 'options':'PGOPTIONS', 'application_name':'PGAPPNAME',
        'sslmode':'PGSSLMODE', 'requiressl':'PGREQUIRESSL', 'sslcompression':'PGSSLCOMPRESSION',
        'sslcert':'PGSSLCERT', 'sslkey':'PGSSLKEY', 'sslrootcert':'PGSSLROOTCERT', 
        'sslcrl':'PGSSLCRL', 'requirepeer':'PGREQUIREPEER', 'krbsrvname':'PGKRBSRVNAME',
        'gsslib':'PGGSSLIB', 'connect_timeout':'PGCONNECT_TIMEOUT',
        'client_encoding':'PGCLIENTENCODING', 'datestyle':'PGDATESTYLE',
        'timezone':'PGTZ', 'geqo':'PGGEQO', 'sysconfdir':'PGSYSCONFDIR',
        'localedir':'PGLOCALEDIR', 'psql_path': '', 'prompt_for_password': '',
        'warn_on_empty_password':'', 'output_to_newfile':'', 'files': '' 
    }

    @property
    @staticmethod
    def postgres_variables(cls):
        return __postgres_variables.copy()

    def __new__(cls, window=None, *args, **kwargs):
        if window is not None:
            if window.id() not in cls.__windows:
                cls.__windows[window.id()] = MutableMapping.__new__(cls, *args, **kwargs)
            return cls.__windows[window.id()]
        return MutableMapping.__new__(cls, *args, **kwargs)

    def __init__(self, *args, **kwargs):
        self.__defaults = {}
        self.__userspecified = {}
        self.output_lock = Lock()
        self.__reload()
        kwargs.pop('window', None)
        self.update(dict(*args, **kwargs))


    @classmethod
    def window_closed(self, window):
        if window.id() in self.__windows:
            del self.__windows[window.id()]

    @classmethod
    def __get_settings(cls):
        if cls.__settings is None:
            cls.__settings = load_settings(cls.__settings_name)
            cls.__settings.clear_on_change('reload')
            cls.__settings.add_on_change('reload', cls.__reload_all_windows)
        return cls.__settings

    @classmethod
    def __reload_all_windows(cls):
        for window in cls.__windows:
            cls.__windows[window].__reload()


    @classmethod
    def __try_validate_name(cls, name):
        return name in cls.__postgres_variables

    @classmethod
    def __validate_name(cls, name):
        if not cls.__try_validate_name(name):
            raise ValueError('Argument ' + name + ' not recognized.')

    def __getitem__(self, name):
        self.__validate_name(name)
        return self.__get(self.__keytransform__(name))

    def __setitem__(self, name, value):
        self.__validate_name(name)
        self.__defaults[self.__keytransform__(name)] = value

    def __delitem__(self, name):
        self.__validate_name(name)
        del self.__defaults[self.__keytransform__(name)]

    def __iter__(self):
        return iter(self.__defaults)

    def __len__(self):
        return len(self.__defaults)

    def __contains__(self, name):
        self.__validate_name(name)
        if self.__keytransform__(name) in self.__defaults:
            return True
        else:
            value = self.__get_settings().get('default_'+name)
            if value:
                return True
        return False

    def __keytransform__(self, name):
        return name

    def __get(self, name):
        if self.__keytransform__(name) not in self.__defaults:
            value = self.__get_settings().get('default_'+name)
            if value:
                self.__defaults[self.__keytransform__(name)] = value
        return self.__defaults[self.__keytransform__(name)]

    def __reload(self):
        self.__defaults = self.__userspecified.copy()

    def save(self):
        updates = False
        for name in self.__userspecified:
            updates = True
            self.__get_settings().set('default_' + name, self.__userspecified[name])
        if updates:
            save_settings(self.__settings_name)
            self.clear()

    def clear(self):
        self.__userspecified = {}
        self.__reload()

    def has_user_specified(self):
        return len(self.__userspecified) > 0

    def set_user_specified(self, name, value):
        self.__validate_name(name)
        self.__userspecified[name] = value

    def unset_user_specified(self, name):
        self.__validate_name(name)
        if name in self.__userspecified:
            del self.__userspecified[name]

class PsqlCommand(PsqlBaseTextCommand):  
    def description(self):
        return 'Executes PostgreSQL commands directly from the editor'

    def run(self, edit, *args, **kwargs):  
        self.edit = edit
        kwargs['window'] = self.window
        self.settings = kwargs
        self.encoding = self.view.encoding()
        if self.encoding == 'Undefined':
            self.encoding = 'UTF-8'

        password = None
        if 'password' in self.settings:
            password = self.settings['password']
        elif self.__is_password_required():
            self.set_status('Enter password for PostgreSQL database.')
            self.window.show_input_panel('Enter password:', '', self.__run_with_password, None, self.__cancelled)
            return
        self.__run_with_password(password)

    def __cancelled(self):
        self.__run_with_password(None)

    def is_output_to_newfile(self):
        return 'output_to_newfile' in self.settings and self.settings['output_to_newfile'] 

    def __is_password_required(self):
        return 'prompt_for_password' in self.settings and self.settings['prompt_for_password'] and 'passfile' not in self.settings and 'service' not in self.settings and not isfile(expanduser('~/.pgpass'))

    def __run_with_password(self, password):
        if not password and self.__is_password_required():
            if 'warn_on_empty_password' in self.settings and self.settings['warn_on_empty_password'] and not ok_cancel_dialog('Proceed with empty password?', 'Proceed'):
                self.set_status('PostgreSQL query cancelled.')
                return
        elif 'password' not in self.settings:
            self.settings['password'] = password

        if not self.is_output_to_newfile():
            self.output_panel = self.window.create_output_panel('psql')
            self.output_panel.set_scratch(True)
            self.output_panel.run_command('erase_view')
            self.output_panel.set_encoding(self.encoding)

        self.set_status('PostgreSQL query executing...')
        thread_infos = []
        thread_num = 0

        if 'files' in self.settings:
            for fileobj in self.settings['files']:  
                if isfile(fileobj):
                    thread_num += 1
                    thread = self.__PostgresQueryExecute(self, file=fileobj)
                    thread_infos.append({'thread': thread, 'file': fileobj})

        else:
            noSelections = True
            for sel in self.view.sel():  
                if not sel.empty():
                    thread_num += 1
                    noSelections = False
                    # Get the selected text  
                    query = self.view.substr(sel)
                    thread = self.__PostgresQueryExecute(self, query=query)
                    thread_infos.append({"thread": thread, "thread_num": thread_num})

            if noSelections:
                thread_num += 1
                # Get all the text  
                query = self.view.substr(Region(0, self.view.size()))
                thread = self.__PostgresQueryExecute(self, query=query)
                thread_infos.append({"thread": thread, "thread_num": thread_num})

        for thread_info in thread_infos:
            thread_info['start_time'] = time()
            thread_info['thread'].start()

        self.__PostgresQueryHandleExecution.execute(thread_infos, thread_num)

    class __PostgresQueryHandleExecution(Thread):
        def __init__(self, thread_infos, thread_total):
            self.thread_infos = thread_infos
            self.thread_total = thread_total
            Thread.__init__(self)

        def run(self):
            new_thread_infos = []
            for thread_info in self.thread_infos:
                if thread_info['thread'].is_alive():
                    new_thread_infos.append(thread_info)
                    continue
                else:
                    completion_time = (time() - thread_info['start_time']) * 1000
                    if 'file' in thread_info:
                        dirpath, filename = split(thread_info['file'])
                        query_id = ('file ' + filename)
                    else:
                        query_id = ('query '+ thread_info['thread_num'] + '/' + self.thread_total) if thread_info['thread_num'] != 1 and self.thread_total != 1 else 'query '
                    self.set_status('PostgreSQL ' + query_id + ' completed in '+ str(completion_time) +' ms.')

            if len(new_thread_infos) > 0:
                self.execute(new_thread_infos, self.thread_total)

        @classmethod
        def execute(cls, thread_infos, thread_total):
            thread = cls(thread_infos, thread_total)
            thread.start()

    class __PostgresQueryExecute(Thread):
        def __init__(self, parent, query=None, file=None):
            self.parent = parent
            self.query = query
            self.file = file
            Thread.__init__(self)

        def __get_parameter(self, name, default=False):
            if name not in self.parent.settings and default:
                self.parent.settings[name] = default
            return self.parent.settings[name] if default or name in self.parent.settings else False


        def __try_add_parameter_name_to_environment(self, env, name, argname, default=False):
            value = self.__get_parameter(name, default)

            if value:
                env[argname] = value
                return True
            return False

        def __output(self, return_code, output_text):
            if self.parent.is_output_to_newfile():
                view = self.parent.window.new_file()
                view.set_scratch(True)
                view.set_encoding(self.parent.encoding)
                view.run_command('append', {'characters': output_text})
                self.parent.window.focus_view(view)
            else:
                self.parent.settings.output_lock.acquire()
                self.parent.output_panel.run_command('append', {'characters': output_text})
                self.parent.window.run_command('show_panel', {'panel': 'output.psql'})
                self.parent.settings.output_lock.release()

        def run(self):
            errored = False

            try:
                cmd = [self.__get_parameter('psql_path', '/usr/bin/psql'), '--no-password'] 
                environment = environ.copy()

                for name in self.parent.settings.postgres_variables:
                    if name in self.parent.settings and self.parent.settings[name]:
                        self.__try_add_parameter_name_to_environment(environment, name, self.parent.settings.postgres_variables[name])

                client_encoding_name = self.parent.settings.postgres_variables['client_encoding']
                if client_encoding_name not in environment:
                    environment[client_encoding_name] = self.parent.encoding

                
                if (self.file): 
                    with open(self.file) as inputfile:
                        psqlprocess = Popen(cmd, stdin=inputfile, stdout=PIPE, stderr=STDOUT, env=environment)
                        stdout, stderr = psqlprocess.communicate()
                else:
                    psqlprocess = Popen(cmd, stdin=PIPE, stdout=PIPE, stderr=STDOUT, env=environment)
                    stdout, stderr = psqlprocess.communicate(bytes(self.query, self.parent.encoding))

                output_text = stdout.decode(self.parent.encoding)
                retcode = psqlprocess.poll()

            except BaseException as e:
                errored = True
                output_text = format_exc()
                retcode = 1


            set_timeout(lambda:self.__output(retcode, output_text), 0)
        

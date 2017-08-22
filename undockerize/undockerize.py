import argparse
import urllib.parse
import os.path
import urllib.request
import shutil
import re
from subprocess import call as subprocess_call, PIPE


class Docker:
    """
    Docker Class
    ----------------------------------------
    Holds the Docker file info and parses it all
    """
    def __init__(self, file_name, dir_str):
        """
        Instantiates an array with all of the lines in the given docker file
        """
        ########################
        #     instance vars    #
        ########################
        # array of the lines in the dockerfile
        self.docker_file = []
        # array of converted file
        self.ansible_file = ['---']
        # current working directory for ansible
        self.work_dir = '~/'
        # the from line in the file
        self.FROM = ''
        # where the dependencies are located (root of Dockerfile)
        self.dir_str = dir_str
        # holds comments until empty line or a command
        self.current_comments = []
        # Dictionary of environment vars set throughout the script
        self.all_env_vars = {}
        # different cases for the docker file syntax
        self.cases = {
                        'ADD': self.ADD,
                        'COPY': self.COPY,
                        'ENV': self.ENV,
                        'RUN': self.RUN,
                        'WORKDIR': self.WORKDIR
                     }
        # Read the file in and put the lines in the docker_file array
        with open(file_name, 'r') as f:
            for line in f:
                line = line.strip()
                self.docker_file.append(line)
                split_line = line.split()
                if len(split_line) > 0 and split_line[0] == 'FROM':
                    self.FROM = line

    def parse_docker(self):
        """
        Parses each line of docker to return the ansible file array
        """
        docker_file = self.docker_file
        ansible_file = self.ansible_file
        current_comments = self.current_comments
        cases = self.cases

        # Check each line for command, run cooresponding function
        x = 0
        while x < len(docker_file):
            line_split = docker_file[x].split()
            if len(line_split) > 0:
                command = line_split[0]
                if command in cases:
                    # each function returns the next spot to go to
                    # (handles multi-line commands)
                    x = cases[command](x)
                elif '#' in command:
                    current_comments.append(docker_file[x])
                elif 'FROM' not in command:
                    # Append any unhandled commands as comments
                    ansible_file.append(
                        '# *****UNDOCKERIZE*****: !!MISSING COMMAND!!: '
                        + docker_file[x])
            else:  # must be empty line
                del current_comments[:]
            x += 1
        del self.ansible_file[-1]  # remove the last \n

    """----------------------COMMANDS------------------"""
    def ADD(self, x):
        """
        Logic for an ADD command (Can copy, download from remote, or unarchive)
        """
        add_cmd, new_x = self.condense_multiline_cmds(x)
        if self.is_square_brackets(add_cmd):
            srcs, dest = self.square_brackets_split(add_cmd)
        else:
            split = add_cmd.split()
            srcs = split[:-1]
            dest = split[-1]

        if self.is_relative_path(dest):
            dest = self.work_dir + '/' + dest
        for src in srcs:
            cmd, _type = self.ADD_helper(src, dest)
            name = self.ADD_name_helper(_type, src, dest)
            self.put_together('ADD', name=name, cmd=cmd)
        return new_x

    def COPY(self, x):
        """
        Logic for a COPY command (Copies file to another location)
        """
        docker_cp_cmd, new_x = self.condense_multiline_cmds(x)
        if self.is_square_brackets(docker_cp_cmd):
            srcs, dest = self.square_brackets_split(docker_cp_cmd)
        else:
            split = docker_cp_cmd.split()
            srcs = split[:-1]
            dest = split[-1]
        if self.is_relative_path(dest):
            dest = self.work_dir + '/' + dest
        cmd = self.COPY_helper(srcs, dest)
        name = self.COPY_name_helper(srcs, dest)
        self.put_together('COPY', name=name, cmd=cmd)
        return new_x

    def ENV(self, x):
        """
        Logic for a ENV command (Sets environment variables)
        """
        env_cmd, new_x = self.condense_multiline_cmds(x)
        env_vars, spaced = self.ENV_helper(env_cmd)

        # Add the env vars to the dictionary
        _vars, _vals = self.ENV_parser(env_vars)
        for x in range(0, len(_vars)):
            # Replace other env vars with the values if set above them
            # ex: Replace $TEST with the value of $TEST
            other_env_vars = self.find_env_vars(_vals[x])
            for _var in other_env_vars:
                val_of_other_var = self.all_env_vars.get(_var)
                if val_of_other_var is not None:
                    _vals[x] = _vals[x].replace('$' + _var, val_of_other_var)
            # Save to the dictionary
            self.all_env_vars[_vars[x]] = _vals[x]

        cmd = []
        cmd.append('  lineinfile:')
        cmd.append('    dest: ~/.bashrc')
        cmd.append("    line: 'export "+env_vars+"'")
        name = self.ENV_name_helper(env_vars, spaced)
        self.put_together('ENV', name=name, cmd=cmd)
        return new_x

    def RUN(self, x):
        """
        Logic for a RUN command (Shell command)
        """
        shell_cmd, new_x = self.condense_multiline_cmds(x)
        cmd = '  shell: '+self.get_work_dir_cmd()
        cmd += shell_cmd
        name = 'Shell Command (' + ' '.join(shell_cmd.split()[0:5]) + ')'
        self.put_together('RUN', name=name, cmd=[cmd])
        return new_x

    def WORKDIR(self, x):
        """
        Logic for a WORKDIR command (change dir for next commands)
        Supposed to work for RUN, CMD, ENTRYPOINT, COPY, ADD
        """
        _dir, new_x = self.condense_multiline_cmds(x)
        if self.is_relative_path(_dir):
            self.work_dir += '/' + _dir
        else:
            self.work_dir = _dir
        name = 'Working dir- ' + self.work_dir
        cmd = '  shell: mkdir -p ' + self.work_dir
        self.put_together('WORKDIR', name=name, cmd=[cmd])
        return new_x

    """----------------COMMAND HELPER FUNCTIONS--------------"""
    def ADD_helper(self, src, dest):
        """
        Determines if you need to get from remote location,
        unarchive a tar, or just copy and returns the cmd,
        along with what type it was for naming later
        """
        if self.is_url(src):
            cmd = []
            cmd.append('  get_url:')
            cmd.append('    url: ' + src)
            cmd.append('    dest: ' + dest)
            return cmd, 'url'
        elif self.is_tar(src):
            cmd = []
            cmd.append('  unarchive:')
            cmd.append('    src: ' + src)
            cmd.append('    dest: ' + dest)
            return cmd, 'tar'
        else:
            return self.COPY_helper([src], dest), 'copy'

    def ADD_name_helper(self, _type, src, dest):
        """
        Returns name based on if getting from url, unarchiving, or copying
        """
        if _type == 'url':
            return 'Download file from ' + src + ' to ' + dest
        elif _type == 'copy':
            return self.COPY_name_helper([src], dest)
        elif _type == 'tar':
            return 'Unarchive ' + src + ' to ' + dest

    def comments(self):
        """
        Appends the current_comments to the ansible file
        """
        ansible_file = self.ansible_file
        comments = self.current_comments

        if len(comments) > 0:
            for comment in comments:
                ansible_file.append(comment)
            del comments[:]

    def condense_multiline_cmds(self, x):
        """
        Account for backslashes to condense multiline command into one line
        """
        docker_file = self.docker_file

        line = ''
        while True:  # breaks after there are no more escaped new lines
            line_split = docker_file[x].split()
            if line_split[0] in self.cases:  # Remove cases from split
                line_split = line_split[1:]
            if '#' in line_split[0]:  # ignore comments
                x += 1
            elif line_split[len(line_split)-1] == '\\':  # Has backslash
                # Only add if there is more than just a backslash
                if len(line_split) > 1:
                    line += ' '.join(line_split[:len(line_split)-1]) + ' '
                x += 1
            else:  # End of a statement
                line += ' '.join(line_split)
                break
        return line, x

    def COPY_helper(self, srcs, dest):
        """
        COPY allows for COPY <src> <src>... <dest>
        Checks for copying multiple files at once
        Returns the copy command
        """
        cmd = []
        cmd.append('  copy:')
        cmd.append('    src: "{{item}}"')
        cmd.append('    dest: ' + dest)
        cmd.append('    mode: 0744')
        cmd.append('  with_fileglob:')
        for src in srcs:  # add all sources to fileglob
            if not os.path.exists(src):
                src = self.dir_str + '/' + src
                if not os.path.isfile(src):
                    print('WARNING: Possible copy issue with file:' + src)
            cmd.append('    - ' + src)
        return cmd

    def COPY_name_helper(self, srcs, dest):
        """
        Returns name with the src and dest in title
        """
        return 'Copy ' + ' '.join(srcs) + ' to ' + dest

    def ENV_helper(self, line):
        """
        ENV allows for either ENV VAR=val or ENV VAR val
        Change format to VAR=val for ansible
        """
        line_split = line.split()

        # Space assignment, change to export FOO="foo bar"
        if '=' not in line_split[0]:
            var = line_split[0]
            val = ' '.join(line_split[1:])
            return ''.join(var + '="' + val + '"'), True
        else:  # uses ENV equals assignment, already good
            return line, False

    def ENV_name_helper(self, env_vars, spaced):
        """
        Returns name with all ENV vars in title

        regex explanation:
        ([a-zA-Z0-9_]+)=# capture something with one or more env allowed chars followed by =
        The rest is to make sure that the above capture isn't surrounded with quotes
        Found at: https://stackoverflow.com/questions/15464299/regex-expression-to-match-even-number-of-double-quotation-not-match-single-o
        (?=              #Only if the following regex matches
        (?:              #match
        [^"]*"           #Any number of quotes followed by a quotes
        [^"]*"           #Again to make sure even number of quotes
        )*               #as many times as needed
        [^"]*$)          #match the remaining non-quote characters until the end of the string
        """  # NOQA
        regex = r'([a-zA-Z0-9_]+)=(?=(?:[^"]*"[^"]*")*[^"]*$)'
        found_vars = re.findall(regex, env_vars)
        return 'Set ENV vars- ' + ' '.join(found_vars)

    def ENV_parser(self, env_vars):
        """
        Straight Hell incarniate
        This function hopefully takes an export ENV command and splits it
        into variables and values
        """
        env_vars += ' '  # add space at end so everything will append
        open_quote = False
        last_backslash = False
        is_var = True
        _vars = []
        _vals = []

        word = ''
        for char in env_vars:
            if is_var and char == '=':  # end of a var
                _vars.append(word)
                word = ''
                is_var = False
            elif is_var and char != ' ':
                word += char
            elif is_var:  # must be space between val and var
                continue
            # everything after this is a value
            elif char == '"':
                open_quote = not open_quote
                if open_quote is False:
                    _vals.append(word)
                    word = ''
                    is_var = True
            elif open_quote:
                word += char
            # everything after this is not in quotes
            elif char == '\\' and not last_backslash:
                last_backslash = True
            elif last_backslash:  # escaped char
                word += char
                last_backslash = False
            elif char == ' ':  # space but not escaped
                _vals.append(word)
                word = ''
                is_var = True
            else:  # add every other char
                word += char
        return _vars, _vals

    def find_env_vars(self, cmd):
        """
        Regex expression to find env variables
        """
        return re.findall(r'[$]([a-zA-Z0-9_]+)', cmd)

    def get_work_dir_cmd(self):
        """
        Returns either '' or 'cd work_dir && '
        """
        work_dir = self.work_dir
        if work_dir != '~/':
            return 'cd ' + work_dir + ' && '
        else:
            return ''

    def is_relative_path(self, path):
        """
        Returns true if path doesn't start with '/' or ~ (must be relative)
        """
        return path[0] != '/' and path[0] != '~'

    def is_square_brackets(self, cmd):
        """
        Returns true if cmd uses ["<src>",..."<dest>"] format
        """
        return cmd[0:2] == '["'

    def is_tar(self, _file):
        """
        Return true if _file is a tar archive. Can only go by file name
        """
        extensions = ['.tar', '.gz', '.bz2', '.xz']
        for ext in extensions:
            if _file.endswith(ext):
                return True
        return False

    def is_url(self, url):
        """
        Determines if an input is a url
        """
        return urllib.parse.urlparse(url).scheme != ""

    def put_together(self, _type, name, cmd):
        """
        The common stuff of every command
        Adds the comments above, then the name and
        command lines to the ansible_file array
        """
        ansible_file = self.ansible_file

        self.comments()
        ansible_file.append('- name: ' + name)
        need_env_vars = {}
        need_environment = False
        for line in cmd:
            ansible_file.append(line)
            # env_var stuff
            poss_vars = self.find_env_vars(line)
            for _var in poss_vars:
                poss = self.all_env_vars.get(_var)
                if poss is not None and need_env_vars.get(_var) is None:
                    need_env_vars[_var] = poss
                    if not need_environment:
                        need_environment = True
        if need_environment and _type != 'ENV':
            ansible_file.append('  environment:')
            for _var, _val in need_env_vars.items():
                # ansible doesn't handle tildes for env vars correctly
                # without filter
                if '~' in _val:
                    _val = '{{ "' + _val + '" | expanduser }}'
                ansible_file.append('    ' + _var + ': ' + _val)
        ansible_file.append('')  # New line after command

    def square_brackets_split(self, cmd):
        """
        Breaks the square brackets notation into srcs and dest
        """
        cmd = cmd[1:-1]  # remove square brackets
        open_quote = False
        split_cmd = []

        word = ''
        for char in cmd:
            if char == '"':
                open_quote = not open_quote
            if open_quote and char != '"':
                if char == ' ':
                    word += '\\'  # escape spaces
                word += char
            if not open_quote and char == '"':
                split_cmd.append(word)
                word = ''
        return split_cmd[:-1], split_cmd[-1]


class Ansible:
    """
    Ansible Class
    ----------------------------------------
    Holds the ansible info and writes the array to the yml file
    """
    def __init__(self, ansible_array, env_vars):
        """
        Instantiates Ansible object
        """
        self.ansible = ansible_array
        self.env_vars = env_vars

    def write_to_file(self, file_name):
        """
        Writes self.ansible to a .yml Ansible file
        """
        # remove .yml if it was included
        if file_name[len(file_name)-4:] == '.yml':
            file_name = file_name[:len(file_name)-4]

        # Make dirs if not a path
        final_dir = '/'.join(file_name.split('/')[:-1])
        if not os.path.isdir(final_dir) and final_dir != '':
            os.makedirs(final_dir)

        # write the ansible array to the file
        with open(file_name + '.yml', 'w') as f:
            for line in self.ansible:
                f.write(line + '\n')


"""------------------------------FROM STUFF--------------------------------"""


def clean_workspace():
    """
    Deletes directories and files made by UnDockerized
    """
    if os.path.isfile('site.yml'):
        os.remove('site.yml')
    if os.path.isdir('roles'):
        shutil.rmtree('roles')
    if os.path.isdir(dependencies_dir):
        shutil.rmtree(dependencies_dir)


def dependencies_copy(repo, dir_str):
    """
    Copies the parent folder of the Dockerfile into
    the Dependencies directory
    """
    dependencies_repo_dir = dependencies_dir + repo + dir_str
    print(dependencies_repo_dir)

    if os.path.isdir(dependencies_repo_dir):  # Delete the old dir
        shutil.rmtree(dependencies_repo_dir)

    # Make copy of important dir for user
    shutil.copytree(repo + dir_str, dependencies_repo_dir)
    # Delete all subdirs of other versions from Dependencies dir
    for root, subdirs, _ in os.walk(dependencies_repo_dir):
        for subdir in subdirs:
            shutil.rmtree(root + '/' + subdir)


def get_repo_dir_from_docker_lib(repo, tags):
    with open('official-images/library/'+repo, 'r') as f:
        found = False
        for line in f:
            if line.startswith('Tags:'):
                regex_ret = re.findall(r' '+tags+'[ \n,]', line)
                if len(regex_ret) > 0:
                    found = True
            if found and line.startswith('Directory:'):
                return re.findall(r'Directory: (.*)', line)[0]


def get_repos_with_FROM(FROM):
    """
    Recursively go up the chain of turtles until an os image is found (no repo)
    """
    stripped_FROM = ''.join(FROM.split()[1:])
    split_FROM = stripped_FROM.split(':')

    repo = split_FROM[0]
    tags = split_FROM[1]
    dirs = tags.split('-')
    # Make a string to find the correct directory
    dir_str = ''
    version = ''
    for _dir in dirs:
        version += '_' + _dir
        dir_str += '/' + _dir

    # Check if dir exists
    link = 'https://github.com/docker-library/' + repo + '.git'
    try:
        urllib.request.urlopen(link)
    except:
        print('Docker used image:\n        ' + stripped_FROM)
        return

    # Keep cloning repos until it finds on that is an image
    # Must be an image if there is no repo there
    repos.append(repo)
    repo_versions.append(version)

    # clone the repo
    subprocess_call(['git', 'clone', link], stdout=PIPE, stderr=PIPE)

    dir_str = '/' + get_repo_dir_from_docker_lib(repo, tags)
    dependencies_copy(repo, dir_str)

    # instantiate a new Docker object
    docker_file = repo + dir_str + '/Dockerfile'
    docker_files.append(Docker(docker_file, dir_str))

    # recursively call on next FROM statement
    get_repos_with_FROM(docker_files[-1].FROM)


def make_ansible_config_file():
    """
    Makes a config file to make sure long commands don't time out the ssh
    connection
    """
    with open('ansible.cfg', 'w') as f:
        f.write('[defaults]\n')
        f.write('host_key_checking = False\n\n')
        f.write('[ssh_connection]\n')
        f.write(
            'ssh_args = -o ServerAliveInterval=30 -o ServerAliveCountMax=30')


def make_ansible_role_file(tasks):
    """
    Creates a role file (site.yml) given all of the tasks
    """
    with open('site.yml', 'w') as f:
        f.write('---\n')
        f.write('- hosts: all\n')
        f.write('  become: yes\n')
        f.write('  roles:\n')
        for task in tasks:
            f.write('    - ' + task + '\n')


def remove_all_repos():
    """
    Gets rid of all of the repos that were downloaded
    """
    for repo in repos:
        shutil.rmtree(repo)
    shutil.rmtree('official-images')


"""------------------------------------MAIN-----------------------------"""
# command-line argument stuff
# -i for input file
# -o for output file
desc = 'Convert a Dockerfile to Ansible code'
argparser = argparse.ArgumentParser(description=desc)
argparser.add_argument(
    '-i', nargs=1, default=['Dockerfile'], type=str,
    metavar='<input_file>',
    help='The input (Dockerfile) file name; *Default: Dockerfile')
argparser.add_argument(
    '-o', nargs=1, default=['UnDockerized'], type=str,
    metavar='<output_role>',
    help='The output (Ansible) role name; *Default: UnDockerized')
_help = ('*****USE WITH CAUTION!!!***** Will delete everything in the '
         'UnDock_Dependencies folder, everything in the roles folder, and '
         'the site.yml file.')
argparser.add_argument(
    '-c', '--clean', dest='clean', action='store_true', help=_help)
_help = ("Won't convert any Dockerfile. Use in tandem with -c if you just "
         "want to clean the workspace. Will run nothing if used alone (Why"
         " would you want to do that? Maybe you like hitting enter in"
         "terminal).")
argparser.add_argument(
    '-n', '--nobuild', dest='nobuild', action='store_true',
    help=_help)
args = vars(argparser.parse_args())

input_file = args['i'][0]
output_file = args['o'][0]
clean = args['clean']
nobuild = args['nobuild']

dependencies_dir = 'UnDock_Dependencies/'
if clean:
    clean_workspace()
if nobuild:
    exit()

docker_files = []  # Docker objects that are created
repos = []  # Cloned Repo names
repo_versions = []  # Versions to store for yml file names
repo_tasks = []  # Ansible task names to be used for roles


def main():
    # Parse input Dockerfile
    if os.path.isfile(input_file):
        docker_files.append(Docker(input_file, '.'))
    else:
        print('File "' + input_file + '" does not exist. Exiting...')
        exit()

    # Clone the official-images library
    link = 'https://github.com/docker-library/official-images.git'
    subprocess_call(['git', 'clone', link], stdout=PIPE, stderr=PIPE)

    # Recursively get all the repos from FROM statements
    get_repos_with_FROM(docker_files[0].FROM)

    # Write all of the ansible files
    for x in range(0, len(docker_files)):
        docker_file = docker_files[x]
        docker_file.parse_docker()
        ansible_file = Ansible(
            docker_file.ansible_file, docker_file.all_env_vars)

        # Location and file name
        if x == 0:
            repo_tasks.append(output_file)
            file_name = 'roles/' + output_file + '/tasks/main'
        else:
            # x-1: input not included (docker_files[0])
            repo_task = repos[x-1] + repo_versions[x-1]
            repo_tasks.append(repo_task)
            file_name = 'roles/' + repo_task + '/tasks/main'

        ansible_file.write_to_file(file_name)

    # Want roles above this line to run in reverse order
    repo_tasks.reverse()

    # Make the site file
    make_ansible_role_file(repo_tasks)

    # Generates the ansible.cfg file for ssh timeout
    make_ansible_config_file()

    # Get rid of all the cloned git repos
    remove_all_repos()

    # print ansible command to run the generated code
    print('ansible-playbook site.yml -u <user> -i <host>,')


if __name__ == '__main__':
    main()

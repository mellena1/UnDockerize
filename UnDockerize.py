import argparse
import urlparse
import os.path
import urllib
import shutil
from subprocess import call as subprocess_call, PIPE

"""
Docker Class
----------------------------------------
Holds the Docker file info and parses it all
"""
class Docker:
    #Instantiates an array with all of the lines in the given docker file
    def __init__(self, file_name, dir_str):
        #instance vars
        self.docker_file = [] #array of the lines in the dockerfile
        self.ansible_file = ['---'] #array of converted file
        self.work_dir = '~/' #current working directory for ansible
        self.FROM = '' #the from line in the file
        self.dir_str = dir_str #where the dependencies are located (root of Dockerfile)
        self.current_comments = [] #holds comments until empty line or a command
        self.cases = { #different cases for the docker file syntax
                        'ADD'     : self.ADD,
                        'COPY'    : self.COPY,
                        'ENV'     : self.ENV,
                        'RUN'     : self.RUN,
                        'WORKDIR' : self.WORKDIR
                     }
        #Read the file in and put the lines in the docker_file array
        with open(file_name, 'r') as f:
            for line in f:
                line = line.strip()
                self.docker_file.append(line)
                split_line = line.split()
                if len(split_line) > 0 and split_line[0] == 'FROM':
                    self.FROM = line

    #Parses each line of docker to return the ansible file array
    def parse_docker(self):
        docker_file = self.docker_file
        ansible_file = self.ansible_file
        current_comments = self.current_comments
        cases = self.cases

        #Check each line for command, run cooresponding function
        x = 0
        while x < len(docker_file):
            line_split = docker_file[x].split()
            if len(line_split) > 0:
                command = line_split[0]
                if command in cases:
                    x = cases[command](x) #returns the next spot to go to (handles multi-line commands)
                elif '#' in command:
                    current_comments.append(docker_file[x])
                elif 'FROM' not in command: #Append any unhandled commands as comments
                    ansible_file.append('# *****UNDOCKERIZE*****: !!MISSING COMMAND!!: ' + docker_file[x])
            else: #must be empty line
                del current_comments[:]
            x+=1
        del self.ansible_file[-1] # remove the last \n

    """----------------------------------------COMMANDS----------------------------------------"""
    #Logic for an ADD command (Can copy, download from remote, or unarchive)
    def ADD(self, x):
        add_cmd, new_x = self.condense_multiline_cmds(x)
        if self.is_square_brackets(add_cmd):
            srcs, dest = self.square_brackets_split(add_cmd)
        else:
            split = add_cmd.split()
            srcs = split[:-1]
            dest = split[-1]

        copies = []
        for src in srcs:
            cmd, _type = self.ADD_helper(src, dest)
            self.put_together(x, name=self.ADD_name_helper(_type,src,dest), cmd=cmd)
        return new_x

    #Logic for a COPY command (Copies file to another location)
    #Doesn't work with env vars right now
    def COPY(self, x):
        docker_cp_cmd, new_x = self.condense_multiline_cmds(x)
        if self.is_square_brackets(docker_cp_cmd):
            srcs, dest = self.square_brackets_split(docker_cp_cmd)
        else:
            split = docker_cp_cmd.split()
            srcs = split[:-1]
            dest = split[-1]
        cmd = self.COPY_helper(srcs, dest)
        self.put_together(x, name=self.COPY_name_helper(srcs, dest), cmd=cmd)
        return new_x

    #Logic for a ENV command (Sets environment variables)
    def ENV(self, x):
        env_cmd, new_x = self.condense_multiline_cmds(x)
        env_vars, spaced = self.ENV_helper(env_cmd)
        cmd = """  lineinfile:\n    dest: ~/.bashrc\n    line: 'export """+env_vars+"'"
        self.put_together(x, name=self.ENV_name_helper(env_vars, spaced), cmd=cmd)
        return new_x

    #Logic for a RUN command (Shell command)
    def RUN(self, x):
        shell_cmd, new_x = self.condense_multiline_cmds(x)
        if '$' in shell_cmd:
            cmd = '  shell: . ~/.bashrc; '+self.get_work_dir_cmd() #Source bashrc if an env var is mentioned
        else:
            cmd = '  shell: '+self.get_work_dir_cmd()
        cmd += shell_cmd
        name = 'Shell Command (' + ' '.join(shell_cmd.split()[0:5]) + ')'
        self.put_together(x, name=name, cmd=cmd)
        return new_x

    #Logic for a WORKDIR command (change dir for next commands)
    #Works for RUN, CMD, ENTRYPOINT, COPY, ADD
    def WORKDIR(self, x):
        _dir, new_x = self.condense_multiline_cmds(x)
        self.work_dir = _dir
        name = 'Working dir- ' + _dir
        if '$' in _dir: #cut down on bashrc calls
            cmd = '  shell: . ~/.bashrc; mkdir -p ' + _dir
        else:
            cmd = '  shell: mkdir -p ' + _dir
        self.put_together(x, name=name, cmd=cmd)
        return new_x


    """----------------------------------------COMMAND HELPER FUNCTIONS----------------------------------------"""
    #Determines if you need to get from remote location,
    #   unarchive a tar, or just copy and returns the cmd,
    #   along with what type it was for naming later
    def ADD_helper(self, src, dest):
        if self.is_url(src):
            return '  get_url:\n    url: ' + src + '\n    dest: ' + dest, 'url'
        elif self.is_tar(src):
                return '  unarchive:\n    src: ' + src + '\n    dest: ' + dest, 'tar'
        else:
            return self.COPY_helper([src], dest), 'copy'

    #Returns name based on if getting from url, unarchiving, or copying
    def ADD_name_helper(self, _type, src, dest):
        if _type == 'url':
            return 'Download file from ' + src + ' to ' + dest
        elif _type == 'copy':
            return self.COPY_name_helper([src], dest)
        elif _type == 'tar':
            return 'Unarchive ' + src + ' to ' + dest

    #Appends the current_comments to the ansible file
    def comments(self):
        ansible_file = self.ansible_file
        comments = self.current_comments

        if len(comments) > 0:
            ansible_file.append('\n'.join(comments))
            del comments[:]

    #Account for backslashes to condense multiline command into one line
    def condense_multiline_cmds(self, x):
        docker_file = self.docker_file

        line = ''
        while True: #breaks after there are no more escaped new lines
            line_split = docker_file[x].split()
            if line_split[0] in self.cases: #Remove cases from split
                line_split = line_split[1:]
            if '#' in line_split[0]: #ignore comments
                x += 1
            elif line_split[len(line_split)-1] == '\\': #Has backslash
                if len(line_split) > 1: #Only add if there is more than just a backslash
                    line += ' '.join(line_split[:len(line_split)-1]) + ' '
                x += 1
            else: #End of a statement
                line += ' '.join(line_split)
                break
        return line, x

    #COPY allows for COPY <src> <src>... <dest>
    #Checks for copying multiple files at once
    #Returns the copy command
    def COPY_helper(self, srcs, dest):
        cmd =  '  copy:\n'
        cmd += '    src: "{{item}}"\n'
        cmd += '    dest: ' + dest + '\n'
        cmd += '    mode: 0744\n'
        cmd += '  with_fileglob:\n'
        for src in srcs: #add all sources to fileglob
            if not os.path.isfile(src):
                src = self.dir_str + '/' + src
                if not os.path.isfile(src):
                    print('WARNING: Possible copy issue with file:' + src)
            cmd += '    - ' + src + '\n'
        return cmd[:-1] #remove last \n

    #Returns name with the src and dest in title
    def COPY_name_helper(self, srcs, dest):
        return 'Copy ' + ' '.join(srcs) + ' to ' + dest

    #ENV allows for either ENV VAR=val or ENV VAR val
    #Change format to VAR=val for ansible
    def ENV_helper(self, line):
        line_split = line.split()

        if '=' not in line_split[0]: #Space assignment, change to export FOO="foo bar"
            return ''.join(line_split[0] + '="' + ' '.join(line_split[1:]) + '"'), True
        else: #uses ENV equals assignment, already good
            return line, False

    #Returns name with all ENV vars in title
    def ENV_name_helper(self, env_vars, spaced):
        env_var_names = []
        env_vars_split = env_vars.split()

        if spaced: #Only one ENV var being set
            env_var_names.append(env_vars_split[0].split('=')[0])
        else:
            for vals in env_vars_split:
                env_var_names.append(vals.split('=')[0])
        return 'Set ENV vars- ' + ' '.join(env_var_names)

    #Returns either '' or 'cd work_dir && '
    def get_work_dir_cmd(self):
        work_dir = self.work_dir
        if work_dir != '':
            return 'cd ' + work_dir + ' && '
        else:
            return ''

    #Returns true if cmd uses ["<src>",..."<dest>"] format
    def is_square_brackets(self, cmd):
        return cmd[0:2] == '["'

    #Return true if _file is a tar archive. Can only go by file name
    def is_tar(self, _file):
        extensions = {'.tar', '.gz', '.bz2', '.xz'}
        return _file[len(_file)-4:] in extensions or _file[len(_file)-3:] in extensions

    #Determines if an input is a url
    def is_url(self, url):
        return urlparse.urlparse(url).scheme != ""

    #The common stuff of every command
    #Adds the comments above, then the name and
    #   command lines to the ansible_file array
    def put_together(self, x, name, cmd):
        docker_file = self.docker_file
        ansible_file = self.ansible_file

        self.comments()
        ansible_file.append('- name: ' + name)
        ansible_file.append(cmd)
        ansible_file.append('') #New line after command

    #Breaks the square brackets notation into srcs and dest
    def square_brackets_split(self, cmd):
        cmd = cmd[1:-1] #remove square brackets
        open_quote = False
        split_cmd = []

        word = ''
        for char in cmd:
            if char == '"':
                open_quote =  not open_quote
            if open_quote and char != '"':
                if char == ' ':
                    word+='\\' #escape spaces
                word+=char
            if not open_quote and char == '"':
                split_cmd.append(word)
                word = ''
        return split_cmd[:-1], split_cmd[-1]


"""
Ansible Class
----------------------------------------
Holds the ansible info and writes the array to the yml file
"""
class Ansible:
    #Instantiates Ansible object
    def __init__(self, ansible_array):
        self.ansible = ansible_array

    #Writes self.ansible to a .yml Ansible file
    def write_to_file(self, file_name):
        #remove .yml if it was included
        if file_name[len(file_name)-4:] == '.yml':
            file_name = file_name[:len(file_name)-4]

        #Make dirs if not a path
        final_dir = '/'.join(file_name.split('/')[:-1])
        if not os.path.isdir(final_dir) and final_dir != '':
            os.makedirs(final_dir)

        #write the ansible array to the file
        with open(file_name + '.yml', 'w') as f:
            for line in self.ansible:
                f.write(line + '\n')


"""----------------------------------------FROM STUFF----------------------------------------"""
#Copies the parent folder of the Dockerfile into
#   the Dependencies directory
def dependencies_copy(repo, dir_str):
    dependencies_repo_dir = dependencies_dir + repo + dir_str

    if os.path.isdir(dependencies_repo_dir): #Delete the old dir
        shutil.rmtree(dependencies_repo_dir)
    shutil.copytree(repo + dir_str, dependencies_repo_dir) #Make copy of important dir for user
    #Delete all subdirs of other versions from Dependencies dir
    for root, subdirs, _ in os.walk(dependencies_repo_dir):
        for subdir in subdirs:
            shutil.rmtree(root + '/' + subdir)

#Recursively go up the chain of turtles until an os image is found (no repo)
def get_repos_with_FROM(FROM):
    stripped_FROM = ''.join(FROM.split()[1:])
    split_FROM = stripped_FROM.split(':')

    repo = split_FROM[0]
    dirs = split_FROM[1].split('-')
    #Make a string to find the correct directory
    dir_str = ''
    version = ''
    for dir in dirs:
        version += '_'+dir
        dir_str += '/'+dir

    #Check if dir exists
    link = 'https://github.com/docker-library/' + repo + '.git'
    opened_url = urllib.urlopen(link)

    #Keep cloning repos until it finds on that is an image
    if opened_url.getcode() != 404: #Must be an image if there is no repo there
        repos.append(repo)
        repo_versions.append(version)

        subprocess_call(['git', 'clone', link], stdout=PIPE,stderr=PIPE) #clone the repo

        dependencies_copy(repo, dir_str)

        docker_files.append(Docker(repo + dir_str + '/Dockerfile', dependencies_dir + repo + dir_str)) #instantiate a new Docker
        get_repos_with_FROM(docker_files[-1].FROM) #recursively call on next FROM statement
    else: #Print the image that docker used
        print('Docker used image:\n        ' + stripped_FROM)

#Makes a config file to make sure long commands don't time out the ssh connection
def make_ansible_config_file():
    with open('ansible.cfg', 'w') as f:
        f.write('[defaults]')
        f.write('host_key_checking = False')
        f.write('[ssh_connection]\n')
        f.write('ssh_args = -o ServerAliveInterval=60 -o ServerAliveCountMax=60')

#Creates a role file (site.yml) given all of the tasks
def make_ansible_role_file(tasks):
    ansible_role = ['---']
    ansible_role.append('- hosts: all')
    ansible_role.append('  become: yes')
    ansible_role.append('  roles:')
    for task in tasks:
        ansible_role.append('    - ' + task)
    return ansible_role

#Gets rid of all of the repos that were downloaded
def remove_all_repos():
    for repo in repos:
        shutil.rmtree(repo)

"""----------------------------------------MAIN----------------------------------------"""
#Main function
if __name__ == "__main__":
    #command-line argument stuff
    #-i for input file
    #-o for output file
    argparser = argparse.ArgumentParser(description='Convert a Dockerfile to Ansible code')
    argparser.add_argument('-i', nargs=1, default=['Dockerfile'], type=str, metavar='input_file', help='The input (Dockerfile) file name; Default: Dockerfile')
    argparser.add_argument('-o', nargs=1, default=['UnDockerized'], type=str, metavar='output_role', help='The output (Ansible) role name; Default: UnDockerized')
    args = vars(argparser.parse_args())

    input_file = args['i'][0]
    output_file = args['o'][0]

    dependencies_dir = 'UnDock_Dependencies/'

    docker_files = [] #Docker objects that are created
    repos = [] #Cloned Repo names
    repo_versions = [] #Versions to store for yml file names
    repo_tasks = [] #Ansible task names to be used for roles

    #Parse input Dockerfile
    if os.path.isfile(input_file):
        docker_files.append(Docker(input_file, '.'))
    else:
        print('File "' + input_file + '" does not exist. Exiting...')
        exit()

    #Recursively get all the repos from FROM statements
    get_repos_with_FROM(docker_files[0].FROM)

    #Write all of the ansible files
    for x in range(0, len(docker_files)):
        docker_file = docker_files[x]
        docker_file.parse_docker()
        ansible_file = Ansible(docker_file.ansible_file)

        #Location and file name
        if x == 0:
            repo_tasks.append(output_file)
            file_name = 'roles/' + output_file + '/tasks/main'
        else:
            repo_task = repos[x-1] + repo_versions[x-1] #x-1: input not included (docker_files[0])
            repo_tasks.append(repo_task)
            file_name = 'roles/' + repo_task + '/tasks/main'

        ansible_file.write_to_file(file_name)

    #Want roles above this line to run in reverse order
    repo_tasks.reverse()

    #Make the site file
    ansible_role_file = Ansible(make_ansible_role_file(repo_tasks))
    ansible_role_file.write_to_file('site.yml')

    #Generates the ansible.cfg file for ssh timeout
    make_ansible_config_file()

    #Get rid of all the cloned git repos
    remove_all_repos()

    #print ansible command to run the generated code
    print('ansible-playbook site.yml -u <user> -i <host>,')

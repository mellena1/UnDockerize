import argparse
import urlparse
import os.path
import urllib
import shutil
from subprocess import call as subprocess_call, PIPE

"""
Docker Class
-------------
Holds the Docker file info and parses it all
"""
class Docker:
    #Instantiates an array with all of the lines in the given docker file
    def __init__(self, file_name):
        #instance vars
        self.docker_file = []
        self.ansible_file = ['---']
        self.work_dir = '~/'
        self.FROM = ''
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
        cases = self.cases

        #Check each line for command, run cooresponding function
        for x in range(0,len(docker_file)):
            line_split = docker_file[x].split()
            if len(line_split) > 0:
                command = line_split[0]
                if command in cases:
                    cases[command](x)
                    if command != 'WORKDIR': #WORKDIR doesn't append anything
                        ansible_file.append('') #add new line after command
        del self.ansible_file[-1] # remove the last \n

    """--------------------------COMMANDS---------------------------------"""
    #Logic for an ADD command (Can copy, download from remote, or unarchive)
    def ADD(self, x):
        cmd = self.ADD_helper(x)
        if cmd == '':
            self.COPY(x)
        else:
            self.put_together(x, name=self.ADD_name_helper(cmd), cmd=cmd)

    #Logic for a COPY command (Copies file to another location)
    def COPY(self, x):
        cmd = '  shell: . ~/.bashrc; '+self.get_work_dir_cmd()
        docker_cp_cmd = self.condense_multiline_cmds(x)
        cmd += self.COPY_helper(docker_cp_cmd)
        self.put_together(x, name=self.COPY_name_helper(cmd), cmd=cmd)

    #Logic for a ENV command (Sets environment variables)
    def ENV(self, x):
        env_vars, spaced = self.ENV_helper(self.condense_multiline_cmds(x))
        cmd = """  lineinfile:\n    dest: ~/.bashrc\n    line: 'export """+env_vars+"'"
        self.put_together(x, name=self.ENV_name_helper(env_vars, spaced), cmd=cmd)

    #Logic for a RUN command (Shell command)
    def RUN(self, x):
        cmd = '  shell: . ~/.bashrc; '+self.get_work_dir_cmd() #Source bashrc everytime for ENV vars
        shell_cmd = self.condense_multiline_cmds(x)
        cmd += shell_cmd
        name = 'Shell Command (' + ' '.join(shell_cmd.split()[0:2]) + ')'
        self.put_together(x, name=name, cmd=cmd)

    #Logic for a WORKDIR command (change dir for next commands)
    #Works for RUN, CMD, ENTRYPOINT, COPY, ADD
    def WORKDIR(self, x):
        self.work_dir = self.docker_file[x].split()[1]


    """------------------COMMAND HELPER FUNCTIONS-------------------------"""
    #Determines if you need to get from remote location,
    #unarchive a tar, or just copy
    def ADD_helper(self, x):
        docker_file = self.docker_file

        input_cmd = self.condense_multiline_cmds(x)
        split_cmd = input_cmd.split()
        if self.is_url(split_cmd[0]):
            return '  get_url:\n    url: ' + split_cmd[0] + '\n    dest: ' + split_cmd[1]
        elif self.is_tar(split_cmd[0]):
            return '  shell: . ~/.bashrc; tar -x ' + split_cmd[0] + ' ' + split_cmd[1]
        else:
            return ''

    #Returns name based on if getting from url or unarchiving
    def ADD_name_helper(self, cmd):
        if cmd.split()[0] == 'get_url:':
            return 'Copy file from ' + cmd.split()[2]
        else:
            return 'Unarchive ' + cmd.split()[3]

    #Takes all comments from y up and appends them (Usually pass x-1)
    def comments(self, y):
        docker_file = self.docker_file
        ansible_file = self.ansible_file

        #Include comments above the RUN command
        comments = ''
        while y >= 0:
            line_split = docker_file[y].split()
            if len(line_split) > 0 and line_split[0][0] == '#': #Comment line
                comments += ' '.join(line_split) + '\n'
                y -= 1
            else: #No more comments
                comments = comments[:len(comments)-1] #remove last \n
                break

        if comments != '':
            ansible_file.append(comments)

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
        return line

    #COPY allows for COPY <src> <src>... <dest>
    #Checks for copying multiple files at once
    def COPY_helper(self, docker_cp_cmd):
        docker_cp_cmd_split = docker_cp_cmd.split()
        cmd = ''
        if len(docker_cp_cmd_split) > 2:
            for src in docker_cp_cmd_split[:-1]:
                cmd += 'cp ' + src + ' ' + docker_cp_cmd_split[-1] + '; '
            cmd = cmd[:-2] #Remove '; '
        else:
            cmd += 'cp '+docker_cp_cmd
        return cmd

    #Returns name with the src and dest in title
    def COPY_name_helper(self, cmd):
        split_cmd = cmd.split()
        src = split_cmd[len(split_cmd)-2:len(split_cmd)-1]
        dest = split_cmd[len(split_cmd)-1:]
        return 'Copy ' + src[0] + ' to ' + dest[0]

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

        self.comments(x-1)
        ansible_file.append('- name: ' + name)
        ansible_file.append(cmd)


"""
Ansible Class
------------------
Holds the ansible info and writes the array to the yml file
"""
class Ansible:
    def __init__(self, ansible_array):
        self.ansible = ansible_array

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


"""-------------------------------------FROM STUFF------------------------------"""
#Copies the parent folder of the Dockerfile into
#   the Dependencies directory
def dependencies_copy(repo, dir_str):
    dependencies_repo_dir = dependencies_dir + repo + dir_str
    repo_depend_dirs.append(dependencies_repo_dir) #Keep track of where everything is going

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

        docker_files.append(Docker(repo + dir_str + '/Dockerfile')) #instantiate a new Docker
        get_repos_with_FROM(docker_files[-1].FROM) #recursively call on next FROM statement
    else: #Print the image that docker used
        print('Docker used image:\n        ' + stripped_FROM)

#Makes an ansible file that will copy over all of the files in the dependencies dir
def make_ansible_dependecy_copy(repo_depend_dirs):
    ansible_file = ['---']
    for _dir in repo_depend_dirs:
        ansible_file.append('- copy:')
        ansible_file.append('    src: "{{ item }}"')
        ansible_file.append('    dest: ~/')
        ansible_file.append('  with_fileglob:')
        ansible_file.append('    - ' + _dir + '/*')
        ansible_file.append('')
        for _, _, files in os.walk(_dir):
            for _file in files:
                dependecy_files.append(_file)
    del ansible_file[-1]
    return ansible_file

#Makes an ansible file that will delete all files copied in make_ansible_dependecy_copy
def make_ansible_dependecy_destroy(dependecy_files):
    ansible_file = ['---']
    for _file in dependecy_files:
        ansible_file.append('- name: rm ' + _file)
        ansible_file.append('  shell: rm -f ~/' + _file)
        ansible_file.append('')
    return ansible_file

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

"""--------------------------------MAIN------------------------------------------"""
#Main function
if __name__ == "__main__":
    #command-line argument stuff
    #-i for input file
    #-o for output file
    argparser = argparse.ArgumentParser(description='Convert a Dockerfile to Ansible code')
    argparser.add_argument('-i', nargs=1, default=['Dockerfile'], type=str, metavar='input_file', help='The input (Dockerfile) file name; Default: Dockerfile')
    argparser.add_argument('-o', nargs=1, default=['UnDockerized'], type=str, metavar='output_file', help='The output (Ansible) file name; Default: UnDockerized')
    args = vars(argparser.parse_args())

    input_file = args['i'][0]
    output_file = args['o'][0]

    dependencies_dir = 'UnDock_Dependencies/'

    docker_files = [] #Docker objects that are created
    repos = [] #Cloned Repo names
    repo_versions = [] #Versions to store for yml file names
    repo_tasks = [] #Ansible task names to be used for roles
    repo_depend_dirs = [] #Actual dirs that include the version dirs of the dependencies
    dependecy_files = [] #Holds the names of the files getting copied to the remote host

    #Parse input Dockerfile
    if os.path.isfile(input_file):
        docker_files.append(Docker(input_file))
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

    #Ansible file to copy dependencies to remote host
    ansible_dep_copy_file = Ansible(make_ansible_dependecy_copy(repo_depend_dirs))
    ansible_dep_copy_file.write_to_file('roles/deps_copy/tasks/main')
    repo_tasks.append('deps_copy')

    #Want roles above this line to run in reverse order
    repo_tasks.reverse()

    #Ansible file to delete dependencies after the ansible roles are done
    ansible_deps_destroy_file = Ansible(make_ansible_dependecy_destroy(dependecy_files))
    ansible_deps_destroy_file.write_to_file('roles/deps_destroy/tasks/main')
    repo_tasks.append('deps_destroy')

    #Make the site file
    ansible_role_file = Ansible(make_ansible_role_file(repo_tasks))
    ansible_role_file.write_to_file('site.yml')

    #Get rid of all the cloned git repos
    remove_all_repos()

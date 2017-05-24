import argparse
import urlparse
import os.path

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
        self.work_dir = ''
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
                self.docker_file.append(line.strip())

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
        cmd = '  shell: '+self.get_work_dir_cmd()
        cmd += 'cp '+self.condense_multiline_cmds(x)
        self.put_together(x, name=self.COPY_name_helper(cmd), cmd=cmd)

    #Logic for a ENV command (Sets environment variables)
    def ENV(self, x):
        env_vars, spaced = self.ENV_helper(self.condense_multiline_cmds(x))
        cmd = '  shell: export '+env_vars
        self.put_together(x, name=self.ENV_name_helper(env_vars, spaced), cmd=cmd)

    #Logic for a RUN command (Shell command)
    def RUN(self, x):
        cmd = '  shell: '+self.get_work_dir_cmd()
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
            return '  shell: tar -x ' + split_cmd[0] + ' ' + split_cmd[1]
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

        if '=' not in line_split[0]: #Space assignment export FOO="foo bar"
            return ''.join(line_split[0] + '="' + ' '.join(line_split[1:]) + '"'), True
        else: #equals assignment, already good
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
        #write the ansible array to the file
        with open(file_name + '.yml', 'w') as f:
            for line in self.ansible:
                f.write(line + '\n')


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

    #Parse Docker
    if os.path.isfile(input_file):
        docker_file = Docker(input_file)
        docker_file.parse_docker()
    else:
        print('File "' + input_file + '" does not exist. Exiting...')
        exit()

    #Write to Ansible
    ansible_file = Ansible(docker_file.ansible_file)
    ansible_file.write_to_file(output_file)

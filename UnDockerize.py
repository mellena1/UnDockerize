import argparse

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
        self.cases = { #different cases for the docker file syntax
                        'ADD'   : self.COPY,
                        'COPY'  : self.COPY,
                        'ENV'   : self.ENV,
                        'RUN'   : self.RUN
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
                    ansible_file.append('') #add new line after command
        del self.ansible_file[-1] # remove the last \n

    """--------------------------COMMANDS---------------------------------"""
    #Logic for a COPY command (Copies file to another location)
    def COPY(self, x):
        cmd = '  shell: cp '+self.condense_multiline_cmds(x)
        put_together(x, name='ADD', cmd)

    #Logic for a ENV command (Sets environment variables)
    def ENV(self, x):
        cmd = '  shell: export '+self.ENV_helper(self.condense_multiline_cmds(x))
        put_together(x, name='ENV', cmd)

    #Logic for a RUN command (Shell command)
    def RUN(self, x):
        cmd='  shell: ' + self.condense_multiline_cmds(x)
        put_together(x, name='RUN', cmd)


    """------------------COMMAND HELPER FUNCTIONS-------------------------"""
    #Takes all comments from y up and appends them (Usually pass x-1)
    def comments(self, y):
        docker_file = self.docker_file

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

    #ENV allows for either ENV VAR=val or ENV VAR val
    #Change format to VAR=val for ansible
    def ENV_helper(self, line):
        line = line.split()
        output = []
        x = 0
        while x < len(line):
            if '=' not in line[x]:
                output.append(line[x] + '=' + line[x+1])
                x += 2
            else:
                output.append(line[x])
                x += 1
        return ' '.join(output)

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
    argparser.add_argument('-o', nargs=1, default=['unDockerized'], type=str, metavar='output_file', help='The output (Ansible) file name; Default: UnDockerized')
    args = vars(argparser.parse_args())

    #Parse Docker
    docker_file = Docker(args['i'][0])
    docker_file.parse_docker()

    #Write to Ansible
    ansible_file = Ansible(docker_file.ansible_file)
    ansible_file.write_to_file(args['o'][0])

import argparse

class Docker:
    #Returns an array of all of the lines in the docker file
    def __init__(self, file_name):
        #instance vars
        self.docker_file = []
        self.ansible_file = ['---']
        #Read the file in and put the lines in the docker_file array
        with open(file_name, 'r') as f:
            for line in f:
                self.docker_file.append(line.strip())

    #Parses each line of docker to return the ansible file array
    def parse_docker(self):
        docker_file = self.docker_file
        #different cases for the docker file syntax
        cases = {
                    'RUN' : self.RUN
                }

        #Check each line for command, run cooresponding function
        for x in range(0,len(docker_file)):
            line_split = docker_file[x].split()
            if len(line_split) > 0:
                command = line_split[0]
                if command in cases:
                    cases[command](x)

    #Logic for a RUN docker command
    def RUN(self, x):
        docker_file = self.docker_file
        ansible_file = self.ansible_file
        if x > 0 and docker_file[x-1][0] == '#':
            ansible_file.append('- name: ' + docker_file[x-1])
            ansible_file.append('  shell: ' + docker_file[x][3:].strip())
        else:
            ansible_file.append('- name: Run Command')
            ansible_file.append('  shell: ' + docker_file[x][3:].strip())

class Ansible:
    def __init__(self, ansible_array):
        self.ansible = ansible_array

    def write_to_file(self, file_name):
        #remove .yml if it was included
        if file_name[len(file_name)-4:] == '.yml':
            file_name = file_name[:len(file_name)-4]
        #with open(file_name + '.yml', 'w') as f:



#Main
if __name__ == "__main__":
    argparser = argparse.ArgumentParser(description='Convert a Dockerfile to Ansible code')
    argparser.add_argument('-i', nargs=1, default=['Dockerfile'], type=str, metavar='input_file', help='The input (Dockerfile) file name; Default: Dockerfile')
    argparser.add_argument('-o', nargs=1, default=['unDockerized'], type=str, metavar='output_file', help='The output (Ansible) file name; Default: UnDockerized')
    args = vars(argparser.parse_args())

    docker_file = Docker(args['i'][0])
    docker_file.parse_docker()
    print(docker_file.ansible_file)

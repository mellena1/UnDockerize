# UnDockerize
A Python script to convert a Dockerfile to an Ansible-Playbook

## Usage
`UnDockerize.py [-h] [-i input_file] [-o output_file]`</br></br>
`-h or --help: show the help message and exit.`</br>
`-i input_file specifies the input file. Defaults to Dockerfile`</br>
`-o output_file specifies the output file name. Defaults to UnDockeried`

## Capabilities
UnDockerize can currently handle a lot of the built in Dockerfile commands and automatically convert them into Ansible code.

### Undockerize supports the following Dockerfile commands currently:
* **ADD** - Including: pulling from remote locations, unarchiving tar files, and the normal COPY command.

  ***NOTE:*** Because the script can't check the actual files that the Ansible code will run over, the only way for it to check  for tar files is to check for the file extension. This means don't have files with .tar, .gz, .bz2, or .xz in them if they are not tar files or it will error when Ansible runs.
  
* **COPY** - Copies a source file to a destination.

* **ENV** - Sets environment variables.

* **RUN** - Runs a shell command.

* **WORKDIR** - Changes the working directory for all following commands.

## Other features
* **Auto-naming**: UnDockerize does its best to provide each Ansible task with a relevant name to what is being done.
* **Comments**: UnDockerize includes all trailing comments behind a valid command.

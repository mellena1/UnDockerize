# UnDockerize
A Python script to convert a Dockerfile to an Ansible-Playbook

# Requirements
* Python 3

## Usage
`UnDockerize.py [-h] [-i <input_file>] [-o <output_role>] [-c] [-n]`</br></br>

```
-h, --help        show this help message and exit
```

```
-i <input_file>   The input (Dockerfile) file name; *Default: Dockerfile
```

```
-o <output_role>  The output (Ansible) role name; *Default: UnDockerized
```

```
 -c, --clean       *****USE WITH CAUTION!!!***** Will delete everything in
                   the UnDock_Dependencies folder, everything in the roles
                   folder, and the site.yml file.
```

```
 -n, --nobuild     Won't convert any Dockerfile. Use in tandem with -c if you
                   just want to clean the workspace. Will run nothing if used
                   alone (Why would you want to do that? Maybe you like
                   hitting enter in terminal).
```


## Capabilities
UnDockerize can currently handle a lot of the built in Dockerfile commands and automatically convert them into Ansible code.

### Undockerize supports the following Dockerfile commands currently:
* **ADD** - Including: pulling from remote locations, unarchiving tar files, and the normal COPY command.

  ***NOTE:*** Because the script can't check the actual files that the Ansible code will run over, the only way for it to check  for tar files is to check for the file extension. This means don't have files with .tar, .gz, .bz2, or .xz in them if they are not tar files or it will error when Ansible runs.

* **COPY** - Copies a source file from the host to the remote ansible destination.

* **ENV** - Sets environment variables.

* **RUN** - Runs a shell command.

* **WORKDIR** - Changes the working directory for all following commands.

## What happens with FROM?
* UnDockerize will "follow the turtles" recursively until it finds the starting image.

* It will create roles for each Dockerfile layer and in the end create a site.yml file to run them all in the correct order to ensure that your final Dockerfile has all of the needed dependencies.

* UnDockerize will print the name of the image that Docker started with so that you know what OS to start with.

## Environment Variables
* UnDockerize will keep track of all of the environment variables set during the Dockerfile. When they are then used in various other commands, it will use Ansible's way of defining the environment and include them for each command when needed.
* UnDockerize will also add them to your .bashrc file, so that when the instance is launched the environment variables will remain. This can easily be tweaked manually by removing the lineinfile commands in the Ansible file if you so choose so.

## Other features
* **Auto-naming**: UnDockerize does its best to provide each Ansible task with a relevant name to what is being done.
* **Comments**: UnDockerize includes all trailing comments behind a valid command.


## Example
### This Dockerfile gets converted:
```
FROM debian:jessie

RUN rm foo

ENV PATH=blah \
    HI=foo \
    foo=bar \
    fool=baff \
    dsf=asffas

ADD https://raw.githubusercontent.com/docker-library/elasticsearch/master/.travis.yml /
ADD /Foo/$HI.tar /$PATH
ADD Foo /foo/$foo
COPY Foo /foo/foo_copy

WORKDIR ~/new_dir

ADD ["foo bar/foo", "foo.tar", "google.com", "my_dir"]
COPY ["foo bar", "foo", "my_dir"]
```

### into this Ansible code:
```
---
- name: Shell Command (rm foo)
  shell: rm foo

- name: Set ENV vars- PATH HI foo fool dsf
  lineinfile:
    dest: ~/.bashrc
    line: 'export PATH=blah HI=foo foo=bar fool=baff dsf=asffas'

- name: Download file from https://raw.githubusercontent.com/docker-library/elasticsearch/master/.travis.yml to /
  get_url:
    url: https://raw.githubusercontent.com/docker-library/elasticsearch/master/.travis.yml
    dest: /

- name: Unarchive /Foo/$HI.tar to /$PATH
  unarchive:
    src: /Foo/$HI.tar
    dest: /$PATH
  environment:
    PATH: blah
    HI: foo

- name: Copy Foo to /foo/$foo
  copy:
    src: "{{item}}"
    dest: /foo/$foo
    mode: 0744
  with_fileglob:
    - ./Foo
  environment:
    foo: bar

- name: Copy Foo to /foo/foo_copy
  copy:
    src: "{{item}}"
    dest: /foo/foo_copy
    mode: 0744
  with_fileglob:
    - ./Foo

- name: Working dir- ~/new_dir
  shell: mkdir -p ~/new_dir

- name: Copy foo\ bar/foo to ~/new_dir/my_dir
  copy:
    src: "{{item}}"
    dest: ~/new_dir/my_dir
    mode: 0744
  with_fileglob:
    - ./foo\ bar/foo

- name: Unarchive foo.tar to ~/new_dir/my_dir
  unarchive:
    src: foo.tar
    dest: ~/new_dir/my_dir

- name: Copy google.com to ~/new_dir/my_dir
  copy:
    src: "{{item}}"
    dest: ~/new_dir/my_dir
    mode: 0744
  with_fileglob:
    - ./google.com

- name: Copy foo\ bar foo to ~/new_dir/my_dir
  copy:
    src: "{{item}}"
    dest: ~/new_dir/my_dir
    mode: 0744
  with_fileglob:
    - ./foo\ bar
    - ./foo
```

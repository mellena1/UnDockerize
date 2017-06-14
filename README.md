# UnDockerize
A Python script to convert a Dockerfile to an Ansible-Playbook

## Usage
`UnDockerize.py [-h] [-i input_file] [-o output_role]`</br></br>
`-h or --help: show the help message and exit.`</br>
`-i input_file specifies the input file. Defaults to Dockerfile`</br>
`-o output_role specifies the output Ansible role name. Defaults to UnDockeried`

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
ADD /Foo/foo.tar /
ADD /Foo/foo.gz /
ADD /Foo/foo.bz2 /
ADD /Foo/foo.xz /
COPY Foo /foo/foo_copy
ADD Foo /foo/foo

ADD ["foo bar/foo", "foo", "foo bar", "foo bar.tar", "bar"]
```

### into this Ansible code:
```
---
- name: Shell Command (rm foo)
  shell: cd ~/ && rm foo

- name: Set ENV vars- PATH HI foo fool dsf
  lineinfile:
    dest: ~/.bashrc
    line: 'export PATH=blah HI=foo foo=bar fool=baff dsf=asffas'

- name: Download file from https://raw.githubusercontent.com/docker-library/elasticsearch/master/.travis.yml to /
  get_url:
    url: https://raw.githubusercontent.com/docker-library/elasticsearch/master/.travis.yml
    dest: /

- name: Unarchive /Foo/foo.tar to /
  unarchive:
    src: /Foo/foo.tar
    dest: /

- name: Unarchive /Foo/foo.gz to /
  unarchive:
    src: /Foo/foo.gz
    dest: /

- name: Unarchive /Foo/foo.bz2 to /
  unarchive:
    src: /Foo/foo.bz2
    dest: /

- name: Unarchive /Foo/foo.xz to /
  unarchive:
    src: /Foo/foo.xz
    dest: /

- name: Copy Foo to /foo/foo_copy
  copy:
    src: "{{item}}"
    dest: /foo/foo_copy
    mode: 0744
  with_fileglob:
    - ./Foo

- name: Copy Foo to /foo/foo
  copy:
    src: "{{item}}"
    dest: /foo/foo
    mode: 0744
  with_fileglob:
    - ./Foo

- name: Copy foo\ bar/foo to bar
  copy:
    src: "{{item}}"
    dest: bar
    mode: 0744
  with_fileglob:
    - ./foo\ bar/foo

- name: Copy foo to bar
  copy:
    src: "{{item}}"
    dest: bar
    mode: 0744
  with_fileglob:
    - ./foo

- name: Copy foo\ bar to bar
  copy:
    src: "{{item}}"
    dest: bar
    mode: 0744
  with_fileglob:
    - ./foo\ bar

- name: Unarchive foo\ bar.tar to bar
  unarchive:
    src: foo\ bar.tar
    dest: bar
```

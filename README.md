docker-composable
=================

A base (dependency-only) role for deploying `docker-compose` based roles.

Roles using the `docker-compose` plugin (provided by `ansible/docker-roles/toolkit`)
can use this role as a dependency to automate the most common deployment use cases.

Example (of `meta/main.yml`):

    dependencies:
      - role: docker-composable
        role_name: foo
	    compose_data: "{{ foo_compose_data }}"

In most cases, dependent roles will define their compose data in `vars/main.yml`. Roles
may also override the default tasks by passing the `deploy_mode_overrides` variable
and defining their own tasks in `tasks/main.yml`. (More on this below.)


Deploy Mode
-----------

The tasks defined in this role are based on the `deploy_mode` variable, which is used
to specify a deployment use case. Currenty options are:

 - `install` (default) - installs the dependent role
 - `purge` - uninstalls the dependent
 - `prefetch` - pulls docker images for the dependent role


Role Variables
--------------

This role must be invoked (as a dependency) with the following variables:

 - `role_name` is the name of the dependent role; it will be used to save the `docker-compose`
   data on the deployed machines; these files can be used to easily recreate deployed containers.
 - `compose_data` is `docker-compose` [YAML][] data defining the desired containers and images

 [YAML]: https://docs.docker.com/compose/yml/

This role also supports:

 - `deploy_mode` is the type of tasks to invoke; optional and defaults to "install"
 - `deploy_mode_overrides` is a list of deploy modes that will be *SKIPPED*, allowing dependent
   roles to define their own override tasks
 - `keep_images` will bypass Docker image purging if set; use this for faster role debugging.

The following are required for the `freeze` deployment mode (and can be omitted otherwise):

 - `docker_domain` - the domain of the docker registry (e.g. "docker-images.locationlabs.com")
 - `docker_username` - the username to access the docker registry
 - `docker_password` - the password to access the docker registry
 - `release_package_tag` - the tag to use to retag target images
 

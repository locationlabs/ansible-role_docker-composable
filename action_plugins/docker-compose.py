"""
Ansible plugin for managing roles using docker-compose.

Check mode is supported to the extent that changes will not be made,
but not so much that expected changes are computed.

Each role is assumed to have its own docker-compose YAML file defining
some number of Docker containers (and images). The plugin handles managing
the YAML file, the Docker images, and the Docker containers.
"""

DOCUMENTATION = """
---
module: docker-compose
short_description: manage docker compose
description:
   - Manage docker-compose YAML, images, and containers
options:
    data:
        description:
            - docker-compose YAML data (passed as a complex argument)
        required: true
    role:
        description:
            - name of the rule
        required: true
    containers:
        description:
            - desired state of containers; one of 'absent', 'present', 'started', 'restarted'
        required: false
    images:
        description:
            - desired state of images; one of 'absent', 'latest', or 'present'.
        required: false
"""


EXAMPLES = """
- docker-compose:
    role: nginx
    data:
      nginx:
        image: nginx:latest
        ports:
          - 80:80
    images: latest
    containers: started
"""

from tempfile import NamedTemporaryFile

from ansible.callbacks import vv, vvv
from ansible.runner.action_plugins.template import ActionModule as TemplateModule
from ansible.runner.return_data import ReturnData
from ansible.utils import parse_kv


ABSENT = "absent"
LATEST = "latest"
PRESENT = "present"
RESTARTED = "restarted"
STARTED = "started"


class ModuleError(Exception):
    pass


class ActionModule(object):

    def __init__(self, runner):
        self.runner = runner
        self.options = None
        self.changed = False
        self.conn = None
        self.tmp = None
        self.inject = None

    @property
    def basedir(self):
        return self.runner.basedir

    @property
    def docker_compose_directory(self):
        return "/etc/docker-compose/{}".format(self.role)

    @property
    def docker_compose_file(self):
        return "{}/docker-compose.yml".format(self.docker_compose_directory)

    @property
    def role(self):
        return self.options["role"]

    @property
    def data(self):
        return self.options["data"]

    @property
    def images(self):
        return [
            container["image"]
            for container in self.data.values()
            if "image" in container
        ]

    @property
    def images_state(self):
        return self.options.get("images")

    @property
    def containers_state(self):
        return self.options.get("containers")

    def execute_module(self,
                       module_name,
                       module_args,
                       complex_args=None):
        module_response = self.runner._execute_module(
            self.conn,
            self.tmp,
            module_name,
            module_args,
            inject=self.inject,
            complex_args=complex_args,
        )
        return self.handle_module_result(module_response.result)

    def handle_module_result(self, result, changed_if=None, failed_if=None):
        changed = result.get("changed", False)
        failed = result.get("failed", False)
        msg = result.get("msg", result.get("stderr", ""))

        vvv("result: failed={} changed={} msg={}".format(
            failed,
            changed,
            msg,
        ))

        if changed:
            self.changed = True
        if failed:
            raise ModuleError(msg)
        return result

    def create_docker_compose_configuration_directory(self):
        """
        Create directory for role-specific docker-compose.yml files.

        Each role's compose file lives in `/etc/docker-compose/<role>/`
        for clarity and to support container recreation outside of Ansible.
        """
        vv("creating: docker-compose configuration directory for '{}'".format(
            self.role,
        ))
        module_args = "path={} state=directory".format(
            self.docker_compose_directory,
        )
        return self.execute_module("file", module_args)

    def remove_docker_compose_configuration_directory(self):
        """
        Remove directory for role-specific docker-compose.yml files.
        """
        vv("removing: docker-compose configuration directory for '{}'".format(
            self.role
        ))
        module_args = "path={} state=absent".format(
            self.docker_compose_directory,
        )
        return self.execute_module("file", module_args)

    def create_docker_compose_file(self):
        """
        Create the role's docker-compose file.
        """
        vv("creating: docker-compose configuration file for '{}'".format(
            self.role,
        ))

        module = TemplateModule(self.runner)
        with NamedTemporaryFile() as template_file:
            # Create a template file for the YAML data
            template_file.write("{{ data|to_nice_yaml }}\n")
            template_file.flush()

            # Use the template module to create the file from YAML data.
            module_args = "src={} dest={}".format(
                template_file.name,
                self.docker_compose_file,
            )
            module_inject = self.inject.copy()
            module_inject["data"] = self.data
            module_response = module.run(
                self.conn, self.tmp, "template", module_args, inject=module_inject,
            )
            return self.handle_module_result(module_response.result)

    def has_docker_compose_file(self):
        """
        Does the role's docker-compose file exist?
        """
        vv("checking: docker-compose configuration file for '{}'".format(
            self.role,
        ))
        module_args = "path={}".format(
            self.docker_compose_file,
        )
        result = self.execute_module("stat", module_args)
        return result["stat"]["exists"]

    def remove_docker_compose_file(self):
        """
        Remove the role's docker-compose file.
        """
        vv("removing: docker-compose configuration file for '{}'".format(
            self.role,
        ))
        module_args = "path={} state=absent".format(
            self.docker_compose_file,
        )
        return self.execute_module("file", module_args)

    def create_docker_compose_containers(self):
        """
        Create containers using docker-compose.

        Containers will be forcibly recreated if the state is "restarted".

        Note that docker-compose will recreate containers even if the state is
        "started" if it detects a change to the image or configuration data. In
        the event that recreation needs to be suppressed, docker-compose must be
        told explicilty NOT to recreate containers. This behavior is not supported
        at this time.
        """
        vv("creating: docker-compose containers for '{}'".format(
            self.role
        ))
        module_args = "path={} state=started force={}".format(
            self.docker_compose_file,
            "true" if self.containers_state in (RESTARTED,) else "false",
        )
        return self.execute_module("docker-compose", module_args)

    def remove_docker_compose_containers(self):
        """
        Remove containers using docker-compose.
        """
        vv("removing: docker-compose containers for '{}'".format(
            self.role,
        ))
        module_args = "path={} state=absent force=true".format(
            self.docker_compose_file,
        )
        return self.execute_module("docker-compose", module_args)

    def pull_images(self):
        """
        Pull docker images.
        """
        vv("pulling: docker images for '{}'".format(
            self.role,
        ))
        module_args = "state={}".format(
            self.images_state,
        )
        return self.execute_module(
            "docker-images",
            module_args,
            complex_args=dict(images=self.images),
        )

    def remove_images(self):
        vv("removing: docker images for '{}'".format(
            self.role,
        ))
        module_args = "state={}".format(
            self.images_state,
        )
        return self.execute_module(
            "docker-images",
            module_args,
            complex_args=dict(images=self.images),
        )

    def set_options(self, module_args, complex_args):
        parsed_args = parse_kv(module_args)
        if complex_args:
            parsed_args.update(complex_args)

        self.options = {
            key: parsed_args.get(key)
            for key in ["containers", "data", "images", "role"]
        }

        if not self.options["role"]:
            raise ModuleError("role is required")

        if not self.data:
            raise ModuleError("data is required")

    def run(self, conn, tmp, module_name, module_args, inject, complex_args=None, **kwargs):
        """
        Run the action plugin.
        """
        # save standard module args for convenience
        self.conn, self.tmp, self.inject = conn, tmp, inject

        if self.runner.check:
            return ReturnData(
                conn=conn,
                result=dict(failed=False, changed=self.changed, msg="ok")
            )

        try:
            # preserve and validate options
            self.set_options(module_args, complex_args)

            # pull image first (to allow for container restart)
            if self.images_state in (PRESENT, LATEST):
                self.pull_images()

            if self.containers_state in (ABSENT,):
                if self.has_docker_compose_file():
                    self.remove_docker_compose_containers()
                    self.remove_docker_compose_file()
                self.remove_docker_compose_configuration_directory()
            elif self.containers_state in (PRESENT, STARTED, RESTARTED):
                self.create_docker_compose_configuration_directory()
                self.create_docker_compose_file()
                if self.containers_state in (STARTED, RESTARTED):
                    self.create_docker_compose_containers()

            # remove image last (to allow for container removal first)
            if self.images_state in (ABSENT,):
                self.remove_images()

        except ModuleError as error:
            return ReturnData(
                conn=conn,
                result=dict(failed=True, changed=self.changed, msg=error.message)
            )
        else:
            return ReturnData(
                conn=conn,
                result=dict(failed=False, changed=self.changed, msg="ok")
            )

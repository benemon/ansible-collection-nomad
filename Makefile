.PHONY: tree units sanity integration

# ansible-test needs a real ansible_collections/<ns>/<name> directory and lists files through git, so the
# copy lives outside this repository and hidden entries (tooling state, not collection content) stay out of it.
TREE = $(or $(TMPDIR),/tmp)/benemon-nomad/ansible_collections/benemon/nomad
VENV = $(CURDIR)/.venv/bin

tree:
	mkdir -p $(TREE)
	rsync -a --delete --delete-excluded --exclude '.*' --exclude tests/output . $(TREE)/

units: tree
	cd $(TREE) && $(VENV)/ansible-test units --python 3.14 --requirements

sanity: tree
	cd $(TREE) && $(VENV)/ansible-test sanity --python 3.14 --requirements

# Lanes: NOMADPY_TEST_CE_BIN, NOMADPY_TEST_ENT_BIN + NOMAD_LICENSE_PATH. An unset lane is skipped.
integration: tree
	cd $(TREE) && PATH=$(VENV):$$PATH $(VENV)/python tests/integration/run.py --python 3.14

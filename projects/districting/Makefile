PY := .venv/bin/python
EXT := $(shell $(PY) -c "import sysconfig; print(sysconfig.get_config_var('EXT_SUFFIX'))")
TARGET := districting/_refine$(EXT)

$(TARGET): cpp/refine.cpp
	c++ -O3 -march=native -std=c++17 -shared -fPIC -Wall -Wextra \
		$(shell $(PY) -m pybind11 --includes) $< -o $@

.PHONY: clean
clean:
	rm -f districting/_refine*.so

# Website data -> <repo>/public/districting/ (needs output/national + output/citizen; uses mapshaper from the root node_modules).
.PHONY: web
web:
	node web/export.mjs

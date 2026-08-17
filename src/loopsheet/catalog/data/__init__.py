"""Built-in vendor packs.

A data package: each subdirectory is a vendor slug holding one YAML file per
part number. Keep this file and every vendor ``__init__.py`` empty of logic —
they are imported during catalog discovery, so anything executable in one runs
before a single part has been asked for.
"""

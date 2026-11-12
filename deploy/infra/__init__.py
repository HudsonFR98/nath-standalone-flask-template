"""Infrastructure helpers used by the `infra` stage of the GitLab pipeline.

Everything here is standard-library only so it can run in the bare
`python:3.11-slim` and `hashicorp/terraform` CI images without installing
dependencies.
"""

# Platform backend

[![CircleCI](https://circleci.com/gh/Syncano/syncano-platform/tree/devel.svg?style=svg&circle-token=c74c9c8616a61b9a3ba6281b233be2f5783b8284)](https://circleci.com/gh/Syncano/syncano-platform/tree/devel)

## Dependencies

- Python version 3.6+.
- docker 1.13+ and docker-compose (`pip install docker-compose`).

## Testing

- Run `make test` to run code checks and all tests with coverage. 

## Starting locally

- Run `make run` to spin up a test instance locally.

## Deployment

- Run `build-staging` or `make build-production` to build a staging or production image respectively.
- Make sure you have a working `kubectl` installed and configured. During deployment you may also require `gpg` (gnupg) and `envsubst` (gettext).
- Run `make deploy-staging` or `make deploy-production` to deploy relevant image.

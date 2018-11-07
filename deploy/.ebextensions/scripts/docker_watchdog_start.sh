#!/bin/bash
docker pull busybox:latest
supervisorctl start docker_watchdog

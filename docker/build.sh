#!/bin/bash
set -e
set -u
SCRIPTROOT="$( cd "$(dirname "$0")" ; pwd -P )"
cd "${SCRIPTROOT}/.."

docker build --network host -t myochallengeeval_mani_agent_slim -f docker/Dockerfile-slim .
# evalai push myochallengeeval_loco_agent:latest --phase myochallenge2023-locophase1-2105
# evalai push myochallengeeval_mani_agent_slim:latest --phase myochallenge2023-maniphase2-2105 --private
#!/bin/bash
docker build --progress=plain -f Dockerfile.web -t mcp-simple-timeserver:web . 2>&1 | tee build_log.txt
docker images
echo "Saving"
docker save mcp-simple-timeserver:web -o mcp-simple-timeserver.tar 
echo "Compressing"
gzip -9 mcp-simple-timeserver.tar
echo "Done"

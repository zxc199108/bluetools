#!/bin/bash
# Build the Bluetooth agent in C
apt-get install -y libglib2.0-dev libgio2.0-cil-dev 2>/dev/null || true
gcc -o /opt/bluetools/btagent /home/firefly/work/bluetools/btagent.c \
    $(pkg-config --cflags --libs glib-2.0 gio-2.0) 2>&1 || {
    echo "Trying alternative gio package..."
    gcc -o /opt/bluetools/btagent /home/firefly/work/bluetools/btagent.c \
        $(pkg-config --cflags --libs glib-2.0 gio-unix-2.0) 2>&1
}
echo "Done: $(file /opt/bluetools/btagent 2>/dev/null || echo 'build failed')"

#!/bin/bash
# Differential test: real omarchy-plugin-validate (bash+jq) vs validate.py on mutated plugin folders.
cd "$(dirname "$0")"; T=$(mktemp -d); same=0; diff=0
mk(){ rm -rf $T/p; mkdir -p $T/p; echo 'Item{}' > $T/p/BarWidget.qml; echo 'Item{}' > $T/p/Panel.qml; echo "$1" > $T/p/manifest.json; }
while IFS= read -r m; do
  mk "$m"; a=$(bash omarchy-plugin-validate $T/p 2>&1; echo "rc=$?"); b=$(python3 validate.py $T/p 2>&1; echo "rc=$?")
  if [ "$a" == "$b" ]; then same=$((same+1)); else diff=$((diff+1)); echo "DIFF: $m"; echo "  bash: $a"; echo "  py:   $b"; fi
done <<'CASES'
{"schemaVersion":1,"id":"me.x","name":"X","version":"1","kinds":["bar-widget"],"entryPoints":{"barWidget":"BarWidget.qml"}}
{"schemaVersion":"1","id":"me.x","name":"X","version":"1","kinds":["bar-widget"],"entryPoints":{"barWidget":"BarWidget.qml"}}
{"schemaVersion":1.0,"id":"me.x","name":"X","version":"1","kinds":["bar-widget"],"entryPoints":{"barWidget":"BarWidget.qml"}}
{"schemaVersion":2,"id":"me.x","name":"X","version":"1","kinds":["bar-widget"],"entryPoints":{"barWidget":"BarWidget.qml"}}
{"schemaVersion":1,"id":"omarchy.x","name":"X","version":"1","kinds":["bar-widget"],"entryPoints":{"barWidget":"BarWidget.qml"}}
{"schemaVersion":1,"id":"me..x","name":"X","version":"1","kinds":["bar-widget"],"entryPoints":{"barWidget":"BarWidget.qml"}}
{"schemaVersion":1,"id":"-me","name":"X","version":"1","kinds":["bar-widget"],"entryPoints":{"barWidget":"BarWidget.qml"}}
{"schemaVersion":1,"id":"me/x","name":"X","version":"1","kinds":["bar-widget"],"entryPoints":{"barWidget":"BarWidget.qml"}}
{"schemaVersion":1,"id":"","name":"X","version":"1","kinds":["bar-widget"],"entryPoints":{"barWidget":"BarWidget.qml"}}
{"schemaVersion":1,"id":"me.x","version":"1","kinds":["bar-widget"],"entryPoints":{"barWidget":"BarWidget.qml"}}
{"schemaVersion":1,"id":"me.x","name":"X","version":"1","kinds":[],"entryPoints":{"barWidget":"BarWidget.qml"}}
{"schemaVersion":1,"id":"me.x","name":"X","version":"1","kinds":"bar-widget","entryPoints":{"barWidget":"BarWidget.qml"}}
{"schemaVersion":1,"id":"me.x","name":"X","version":"1","kinds":["bar-widget"],"entryPoints":[]}
{"schemaVersion":1,"id":"me.x","name":"X","version":"1","kinds":["bar-widget"],"entryPoints":{"barWidget":"../BarWidget.qml"}}
{"schemaVersion":1,"id":"me.x","name":"X","version":"1","kinds":["bar-widget"],"entryPoints":{"barWidget":"/etc/passwd"}}
{"schemaVersion":1,"id":"me.x","name":"X","version":"1","kinds":["bar-widget"],"entryPoints":{"barWidget":"Nope.qml"}}
{"schemaVersion":1,"id":"me.x","name":"X","version":"1","kinds":["bar-widget"],"entryPoints":{"barWidget":""}}
{"schemaVersion":1,"id":"me.x","name":"X","version":"1","kinds":["bar-widget","panel"],"entryPoints":{"barWidget":"BarWidget.qml"}}
{"schemaVersion":1,"id":"me.x","name":"X","version":"1","kinds":["bar-widget","panel"],"entryPoints":{"barWidget":"BarWidget.qml","panel":"Panel.qml"}}
{"schemaVersion":1,"id":"me.x","name":"X","version":"1","kinds":["bar-widget"],"entryPoints":{"barWidget":"BarWidget.qml"},"barWidget":{"defaultSection":"top"}}
{"schemaVersion":1,"id":"me.x","name":"X","version":"1","kinds":["bar-widget"],"entryPoints":{"barWidget":"BarWidget.qml"},"barWidget":{"defaultSection":"right"}}
{"schemaVersion":1,"id":"me.x","name":"X","version":"1","kinds":["widget"],"entryPoints":{"barWidget":"BarWidget.qml"}}
{"schemaVersion":1,"id":"me.x","name":"X","version":"1","kinds":["bar-widget"],"entryPoints":{"barWidget":"BarWidget.qml"},"barWidget":{"category":"Fun"}}
not json
CASES
mk '{"schemaVersion":1,"id":"me.x","name":"X","version":"1","kinds":["bar-widget"],"entryPoints":{"barWidget":"BarWidget.qml"}}'; ln -s /etc/hosts $T/p/link
a=$(bash omarchy-plugin-validate $T/p 2>&1; echo "rc=$?"); b=$(python3 validate.py $T/p 2>&1; echo "rc=$?"); [ "$a" == "$b" ] && same=$((same+1)) || { diff=$((diff+1)); echo "DIFF symlink: $a / $b"; }
echo "same=$same diff=$diff"; rm -rf $T

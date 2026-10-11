
#!/bin/bash
set -eu

js_escape() {
  printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g'
}

DB_NAME=$(js_escape "$MONGO_APP_DATABASE")
APP_USER=$(js_escape "$MONGO_APP_USERNAME")
APP_PASSWORD=$(js_escape "$MONGO_APP_PASSWORD")

mongosh \
  --username "$MONGO_INITDB_ROOT_USERNAME" \
  --password "$MONGO_INITDB_ROOT_PASSWORD" \
  --authenticationDatabase admin \
  --quiet \
  --eval "
    const databaseName = \"$DB_NAME\";
    const appUsername = \"$APP_USER\";
    const appPassword = \"$APP_PASSWORD\";

    const appDb = db.getSiblingDB(databaseName);

    if (!appDb.getUser(appUsername)) {
      appDb.createUser({
        user: appUsername,
        pwd: appPassword,
        roles: [
          { role: 'readWrite', db: databaseName }
        ]
      });
      print('Usuario de aplicación creado correctamente.');
    }
  "

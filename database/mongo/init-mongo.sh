
#!/bin/bash
set -eu

DB_NAME=$(jq -Rn --arg value "$MONGO_APP_DATABASE" '$value')
APP_USER=$(jq -Rn --arg value "$MONGO_APP_USERNAME" '$value')
APP_PASSWORD=$(jq -Rn --arg value "$MONGO_APP_PASSWORD" '$value')

mongosh \
  --username "$MONGO_INITDB_ROOT_USERNAME" \
  --password "$MONGO_INITDB_ROOT_PASSWORD" \
  --authenticationDatabase admin \
  --quiet \
  --eval "
    const databaseName = $DB_NAME;
    const appUsername = $APP_USER;
    const appPassword = $APP_PASSWORD;

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

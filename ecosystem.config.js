const path = require('path');

module.exports = {
  apps: [{
    name: 'olt-app',
    script: path.join(__dirname, 'app.py'),
    interpreter: path.join(__dirname, 'venv/bin/python'),
    cwd: __dirname,
    autorestart: true,
    watch: false,
  }]
}

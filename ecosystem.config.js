module.exports = {
  apps: [{
    name: 'olt-app',
    script: 'app.py',
    interpreter: 'venv/bin/python',
    cwd: __dirname,
    autorestart: true,
    watch: false,
  }]
}

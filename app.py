import os
import re
import json
import time
import socket
from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit
from models import db, OLT, ONT, QuickCommand, gen_uuid
import olt_service

app = Flask(__name__)
app.config['SECRET_KEY'] = os.urandom(24).hex()
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///olt.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)
socketio = SocketIO(app, cors_allowed_origins='*', ping_timeout=60, ping_interval=25)

with app.app_context():
    db.create_all()
    if not QuickCommand.query.first():
        db.session.add(QuickCommand(label='Init Session', commands=json.dumps(['enable', 'config'])))
        db.session.add(QuickCommand(label='Scan ONT', commands=json.dumps(['display ont autofind all'])))
        db.session.commit()

@app.route('/')
def dashboard():
    olts = OLT.query.all()
    onts = ONT.query.all()
    return render_template('dashboard.html', olts=olts, onts=onts)

@app.route('/olt')
def olt_list():
    olts = OLT.query.all()
    return render_template('olt_list.html', olts=olts)

@app.route('/olt/create', methods=['GET', 'POST'])
def olt_create():
    if request.method == 'POST':
        olt = OLT(
            name=request.form['name'],
            ip=request.form['ip'],
            username=request.form['username'],
            password=request.form['password'],
            type=request.form.get('type', 'Huawei'),
            line_profile_id=request.form.get('line_profile_id', '10'),
            srv_profile_id=request.form.get('srv_profile_id', '10'),
        )
        db.session.add(olt)
        db.session.commit()
        return jsonify({'status': 'ok', 'id': olt.id})
    return render_template('olt_form.html')

@app.route('/olt/<olt_id>/edit', methods=['GET', 'POST'])
def olt_edit(olt_id):
    olt = OLT.query.get_or_404(olt_id)
    if request.method == 'POST':
        olt.name = request.form['name']
        olt.ip = request.form['ip']
        olt.username = request.form['username']
        if request.form.get('password'):
            olt.password = request.form['password']
        olt.type = request.form.get('type', 'Huawei')
        olt.line_profile_id = request.form.get('line_profile_id', '10')
        olt.srv_profile_id = request.form.get('srv_profile_id', '10')
        db.session.commit()
        return jsonify({'status': 'ok'})
    return render_template('olt_form.html', olt=olt)

@app.route('/olt/<olt_id>/delete', methods=['POST'])
def olt_delete(olt_id):
    olt = OLT.query.get_or_404(olt_id)
    db.session.delete(olt)
    db.session.commit()
    return jsonify({'status': 'ok'})

@app.route('/olt/<olt_id>/config')
def olt_config(olt_id):
    olt = OLT.query.get_or_404(olt_id)
    try:
        config = olt_service.get_olt_config(olt)
        return jsonify({'config': config})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/olt/<olt_id>/status')
def olt_status(olt_id):
    olt = OLT.query.get_or_404(olt_id)
    result = olt_service.check_olt_status(olt)
    return jsonify(result)

@app.route('/terminal')
def terminal():
    olts = OLT.query.all()
    return render_template('terminal.html', olts=olts)

@app.route('/ont')
def ont_page():
    olts = OLT.query.all()
    return render_template('ont.html', olts=olts)

@app.route('/api/olt', methods=['GET'])
def api_olt_list():
    olts = OLT.query.all()
    return jsonify([{
        'id': o.id, 'name': o.name, 'ip': o.ip, 'username': o.username,
        'type': o.type, 'line_profile_id': o.line_profile_id,
        'srv_profile_id': o.srv_profile_id, 'onts': [{'id': on.id} for on in o.onts.all()]
    } for o in olts])

@app.route('/api/olt/<olt_id>')
def api_olt_get(olt_id):
    olt = OLT.query.get_or_404(olt_id)
    return jsonify({
        'id': olt.id, 'name': olt.name, 'ip': olt.ip,
        'username': olt.username, 'type': olt.type,
        'line_profile_id': olt.line_profile_id,
        'srv_profile_id': olt.srv_profile_id,
    })

@app.route('/api/olt', methods=['POST'])
def api_olt_create():
    data = request.json
    olt = OLT(
        name=data['name'], ip=data['ip'], username=data['username'],
        password=data['password'], type=data.get('type', 'Huawei'),
        line_profile_id=data.get('line_profile_id', '10'),
        srv_profile_id=data.get('srv_profile_id', '10'),
    )
    db.session.add(olt)
    db.session.commit()
    return jsonify({'id': olt.id}), 201

@app.route('/api/olt/<olt_id>', methods=['PUT'])
def api_olt_update(olt_id):
    olt = OLT.query.get_or_404(olt_id)
    data = request.json
    olt.name = data.get('name', olt.name)
    olt.ip = data.get('ip', olt.ip)
    olt.username = data.get('username', olt.username)
    if data.get('password'):
        olt.password = data['password']
    olt.type = data.get('type', olt.type)
    olt.line_profile_id = data.get('line_profile_id', olt.line_profile_id)
    olt.srv_profile_id = data.get('srv_profile_id', olt.srv_profile_id)
    db.session.commit()
    return jsonify({'status': 'ok'})

@app.route('/api/olt/<olt_id>', methods=['DELETE'])
def api_olt_delete(olt_id):
    olt = OLT.query.get_or_404(olt_id)
    db.session.delete(olt)
    db.session.commit()
    return jsonify({'status': 'ok'})

@app.route('/api/olt/<olt_id>/status')
def api_olt_status(olt_id):
    olt = OLT.query.get_or_404(olt_id)
    return jsonify(olt_service.check_olt_status(olt))

@app.route('/api/olt/<olt_id>/config')
def api_olt_config(olt_id):
    olt = OLT.query.get_or_404(olt_id)
    try:
        return jsonify({'config': olt_service.get_olt_config(olt)})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/ont', methods=['GET'])
def api_ont_list():
    onts = ONT.query.order_by(ONT.created_at.desc()).all()
    return jsonify([{
        'id': o.id, 'olt_id': o.olt_id, 'name': o.name, 'sn': o.sn,
        'slot': o.slot, 'pon': o.pon, 'ont_id': o.ont_id,
        'vlan': o.vlan, 'vlan_ids': o.vlan_ids, 'status': o.status,
        'rx_power': o.rx_power, 'address': o.address,
    } for o in onts])

@app.route('/api/ont/vlans')
def api_ont_vlans():
    return jsonify(['100', '220', '221', '222', '227'])

@app.route('/api/ont/scan/<olt_id>')
def api_ont_scan(olt_id):
    olt = OLT.query.get_or_404(olt_id)
    try:
        results = olt_service.scan_unregistered(olt)
        return jsonify(results)
    except Exception as e:
        return jsonify({'error': str(e), 'details': str(e)}), 500

@app.route('/api/ont', methods=['POST'])
def api_ont_create():
    data = request.json
    ont = ONT(
        olt_id=data['olt_id'], sn=data['sn'],
        name=data.get('name', ''), address=data.get('address', ''),
        vlan_ids=data.get('vlan_ids', ''), status='registered',
    )
    db.session.add(ont)
    db.session.commit()
    return jsonify({'id': ont.id}), 201

@app.route('/api/ont/<ont_id>', methods=['DELETE'])
def api_ont_delete(ont_id):
    ont = ONT.query.get_or_404(ont_id)
    db.session.delete(ont)
    db.session.commit()
    return jsonify({'status': 'ok'})

@app.route('/api/ont/provision', methods=['POST'])
def api_ont_provision():
    data = request.json
    olt = OLT.query.get_or_404(data.get('oltId') or data.get('olt_id'))
    result = olt_service.provision_ont(
        olt, data['slot'], data['pon'], data['sn'], data['vlan'],
        data.get('nama', ''), data.get('alamat', ''),
        data.get('pppoe_user', ''), data.get('pppoe_pass', ''),
        data.get('additional_vlans', ''), data.get('use_tr069', False),
        data.get('tr069_profile', 'acs'),
    )
    if result['status'] == 'success':
        extra_arr = [v.strip() for v in data.get('additional_vlans', '').split(',') if v.strip()]
        if data.get('use_tr069') and '100' not in extra_arr:
            extra_arr.append('100')
        all_vlans = ','.join(filter(None, [data['vlan']] + extra_arr))
        try:
            ont = ONT(
                olt_id=data['olt_id'], sn=data['sn'],
                slot=data['slot'], pon=data['pon'], ont_id=result['ont_id'],
                name=data.get('nama', ''), address=data.get('alamat', ''),
                vlan=data['vlan'], vlan_ids=all_vlans, status='registered',
            )
            db.session.add(ont)
            db.session.commit()
        except Exception as e:
            print(f'DB Error: {e}')
    return jsonify(result)

@app.route('/api/ont/sync', methods=['POST'])
def api_ont_sync():
    data = request.json
    olt = OLT.query.get_or_404(data['oltId'])
    try:
        onts, raw_output = olt_service.get_registered_onts(olt, data['slot'], data['pon'])
        results = []
        for ont in onts:
            try:
                existing = ONT.query.filter_by(olt_id=data['oltId'], sn=ont['sn']).first()
                if existing:
                    existing.slot = data['slot']
                    existing.pon = data['pon']
                    existing.ont_id = ont['ont_id']
                    existing.status = ont.get('status', 'online')
                    existing.rx_power = ont.get('rx_power')
                    existing.vlan = ont.get('vlan', '')
                    existing.vlan_ids = ont.get('vlan', '')
                else:
                    new_ont = ONT(
                        olt_id=data['oltId'], sn=ont['sn'],
                        slot=data['slot'], pon=data['pon'],
                        ont_id=ont['ont_id'], name=ont.get('description', ''),
                        vlan=ont.get('vlan', ''), vlan_ids=ont.get('vlan', ''),
                        status=ont.get('status', 'online'),
                        rx_power=ont.get('rx_power'),
                    )
                    db.session.add(new_ont)
                db.session.commit()
            except Exception as e:
                print(f'Sync DB Error: {e}')
            results.append(ont)
        if not results:
            return jsonify({'error': 'No registered ONTs found', 'raw': raw_output}), 200
        return jsonify(results)
    except Exception as e:
        return jsonify({'error': str(e), 'details': str(e)}), 500

@app.route('/api/ont/delete-from-olt', methods=['POST'])
def api_ont_delete_from_olt():
    data = request.json
    olt = OLT.query.get_or_404(data['oltId'])
    try:
        output = olt_service.delete_ont_from_olt(olt, data['slot'], data['pon'], data['ontId'])
        has_error = bool(re.search(r'(Error|Failure|% Bad)', output, re.I))
        if has_error:
            return jsonify({'error': 'Gagal menghapus ONT dari OLT', 'details': output}), 500
        try:
            ONT.query.filter_by(olt_id=data['oltId'], sn=data.get('sn', '')).delete()
            db.session.commit()
        except:
            ONT.query.filter_by(olt_id=data['oltId'], slot=data['slot'],
                                pon=data['pon'], ont_id=data['ontId']).delete()
            db.session.commit()
        return jsonify({'status': 'success'})
    except Exception as e:
        return jsonify({'error': str(e), 'details': str(e)}), 500

@app.route('/api/ont/olt-registered/<olt_id>/<slot>/<pon>')
def api_ont_olt_registered(olt_id, slot, pon):
    olt = OLT.query.get_or_404(olt_id)
    try:
        onts, raw = olt_service.get_registered_onts(olt, slot, pon)
        db_onts = ONT.query.filter_by(olt_id=olt_id, slot=slot, pon=pon).filter(ONT.ont_id.isnot(None)).all()
        db_map = {d.ont_id: d for d in db_onts}
        result = []
        for ont in onts:
            d = db_map.get(ont['ont_id'])
            result.append({
                'ont_id': ont['ont_id'], 'sn': ont['sn'],
                'slot': slot, 'pon': pon,
                'description': ont.get('description') or (d.name if d else ''),
                'address': d.address if d else '',
                'vlan': ont.get('vlan', '') or (d.vlan if d else ''),
                'rx_power': ont.get('rx_power'),
                'status': ont.get('status', d.status if d else 'unknown'),
            })
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e), 'details': str(e)}), 500

@app.route('/api/ont/registered-db/<olt_id>/<slot>/<pon>')
def api_ont_registered_db(olt_id, slot, pon):
    onts = ONT.query.filter_by(olt_id=olt_id, slot=slot, pon=pon)\
        .filter(ONT.ont_id.isnot(None)).order_by(ONT.ont_id).all()
    return jsonify([{
        'ont_id': o.ont_id, 'sn': o.sn, 'slot': o.slot, 'pon': o.pon,
        'description': o.name or '', 'vlan': o.vlan or '',
        'rx_power': o.rx_power, 'status': o.status or 'unknown',
    } for o in onts])

@app.route('/api/ont/by-olt/<olt_id>')
def api_ont_by_olt(olt_id):
    onts = ONT.query.filter_by(olt_id=olt_id).filter(ONT.ont_id.isnot(None))\
        .order_by(ONT.slot, ONT.pon, ONT.ont_id).all()
    return jsonify([{
        'id': o.id, 'ont_id': o.ont_id, 'sn': o.sn, 'slot': o.slot,
        'pon': o.pon, 'description': o.name or '', 'vlan': o.vlan or '',
        'rx_power': o.rx_power, 'status': o.status or 'unknown',
    } for o in onts])

@app.route('/api/ont/<ont_id>')
def api_ont_detail(ont_id):
    ont = ONT.query.get_or_404(ont_id)
    rx_power = None
    if ont.ont_id is not None and ont.olt_id:
        olt = OLT.query.get(ont.olt_id)
        if olt:
            try:
                rx_power = olt_service.get_ont_optical_info(olt, ont.slot, ont.pon, ont.ont_id)
            except:
                pass
    return jsonify({
        'id': ont.id, 'olt_id': ont.olt_id, 'sn': ont.sn,
        'slot': ont.slot, 'pon': ont.pon, 'ont_id': ont.ont_id,
        'name': ont.name, 'address': ont.address, 'vlan': ont.vlan,
        'vlan_ids': ont.vlan_ids, 'status': ont.status,
        'rx_power': rx_power,
        'olt': {'id': ont.olt.id, 'name': ont.olt.name, 'ip': ont.olt.ip} if ont.olt else None,
    })

@app.route('/api/ont/tr069-config', methods=['POST'])
def api_ont_tr069():
    data = request.json
    olt = OLT.query.get_or_404(data['oltId'])
    try:
        result = olt_service.configure_tr069(olt, data['slot'], data['pon'], data['ontId'], data.get('profile', 'acs'))
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e), 'details': str(e)}), 500

@app.route('/api/quick-commands', methods=['GET'])
def api_quick_commands_list():
    cmds = QuickCommand.query.order_by(QuickCommand.created_at).all()
    return jsonify([{
        'id': c.id, 'label': c.label,
        'commands': json.loads(c.commands),
    } for c in cmds])

@app.route('/api/quick-commands', methods=['POST'])
def api_quick_commands_create():
    data = request.json
    qc = QuickCommand(label=data['label'], commands=json.dumps(data['commands']))
    db.session.add(qc)
    db.session.commit()
    return jsonify({'id': qc.id}), 201

@app.route('/api/quick-commands/<cmd_id>', methods=['PUT'])
def api_quick_commands_update(cmd_id):
    qc = QuickCommand.query.get_or_404(cmd_id)
    data = request.json
    if 'label' in data:
        qc.label = data['label']
    if 'commands' in data:
        qc.commands = json.dumps(data['commands'])
    db.session.commit()
    return jsonify({'status': 'ok'})

@app.route('/api/quick-commands/<cmd_id>', methods=['DELETE'])
def api_quick_commands_delete(cmd_id):
    qc = QuickCommand.query.get_or_404(cmd_id)
    db.session.delete(qc)
    db.session.commit()
    return jsonify({'status': 'ok'})

# ========== WebSocket Terminal ==========
active_connections = {}

@socketio.on('ssh:connect')
def handle_ssh_connect(data):
    sid = request.sid
    host = data.get('host')
    username = data.get('username', 'root')
    password = data.get('password', '')
    port = data.get('port', 22)

    try:
        from netmiko import ConnectHandler
        conn = ConnectHandler(
            device_type='huawei',
            host=host,
            username=username,
            password=password,
            port=port,
            timeout=10,
            global_delay_factor=1,
        )
        conn.enable()
        active_connections[sid] = conn
        emit('ssh:connected', {'message': 'SSH Connection established'})
    except Exception as e:
        import traceback
        traceback.print_exc()
        try:
            import socket as _socket
            tn = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
            tn.settimeout(10)
            tn.connect((host, 23))
            tn.sendall(b'\n')
            time.sleep(1)
            data = b''
            while True:
                try:
                    chunk = tn.recv(4096)
                    if not chunk: break
                    data += chunk
                    if b'name:' in data or b'Username:' in data or b'login:' in data:
                        break
                except _socket.timeout:
                    break
            tn.sendall(username.encode() + b'\n')
            data = b''
            while True:
                try:
                    chunk = tn.recv(4096)
                    if not chunk: break
                    data += chunk
                    if b'assword:' in data:
                        break
                except _socket.timeout:
                    break
            tn.sendall(password.encode() + b'\n')
            time.sleep(1)
            tn.settimeout(None)
            active_connections[sid] = tn
            emit('ssh:connected', {'message': 'Telnet Connection established'})
        except Exception as e2:
            emit('ssh:error', {'message': f'SSH failed: {e}\nTelnet also failed: {e2}'})

@socketio.on('terminal:input')
def handle_terminal_input(data):
    sid = request.sid
    conn = active_connections.get(sid)
    if not conn:
        return
    try:
        if hasattr(conn, 'send_command_timing'):
            output = conn.send_command_timing(data, delay=0.3)
            emit('terminal:data', output)
        elif hasattr(conn, 'recv'):
            conn.sendall(data.encode())
            time.sleep(0.3)
            conn.settimeout(0.5)
            try:
                out = b''
                while True:
                    chunk = conn.recv(4096)
                    if not chunk: break
                    out += chunk
            except:
                pass
            conn.settimeout(None)
            emit('terminal:data', out.decode('ascii', errors='replace'))
        elif hasattr(conn, 'write'):
            conn.write(data.encode())
            time.sleep(0.3)
            try:
                out = conn.read_very_eager().decode('ascii', errors='replace')
                emit('terminal:data', out)
            except:
                pass
    except Exception as e:
        emit('terminal:data', f'\r\nError: {e}\r\n')

@socketio.on('disconnect')
def handle_disconnect():
    sid = request.sid
    conn = active_connections.pop(sid, None)
    if conn:
        try:
            if hasattr(conn, 'disconnect'):
                conn.disconnect()
            elif hasattr(conn, 'close'):
                conn.close()
        except:
            pass

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=3000, debug=True)

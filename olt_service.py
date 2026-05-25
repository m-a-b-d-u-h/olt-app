import re
import socket
import time
from netmiko import ConnectHandler


def _get_netmiko_params(olt):
    return {
        'device_type': 'huawei',
        'host': olt.ip,
        'username': olt.username,
        'password': olt.password,
        'port': 22,
        'timeout': 15,
        'global_delay_factor': 2,
        'conn_timeout': 10,
        'session_timeout': 60,
    }


def _telnet_read_until(tn, patterns, timeout=10):
    data = b''
    tn.settimeout(timeout)
    start = time.time()
    while time.time() - start < timeout:
        try:
            chunk = tn.recv(4096)
            if not chunk:
                break
            data += chunk
            for pat in patterns:
                if isinstance(pat, bytes) and pat.lower() in data.lower():
                    return data, pat
        except socket.timeout:
            break
    return data, None


def _telnet_login(olt):
    tn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    tn.settimeout(10)
    tn.connect((olt.ip, 23))
    time.sleep(0.5)

    data, _ = _telnet_read_until(tn, [b'name:', b'Username:', b'login:'], timeout=8)
    tn.sendall(olt.username.encode() + b'\r\n')

    data, _ = _telnet_read_until(tn, [b'assword:'], timeout=8)
    tn.sendall(olt.password.encode() + b'\r\n')

    data, _ = _telnet_read_until(tn, [b'>', b'#', b']'], timeout=5)
    tn.settimeout(None)
    return tn


def _telnet_send_command(tn, command, delay=3):
    tn.sendall(command.encode() + b'\r\n')
    time.sleep(delay)
    data, _ = _telnet_read_until(tn, [b'>', b'#', b']'], timeout=5)
    lines = data.decode('ascii', errors='replace')
    return lines


def _telnet_shell(olt, commands, delay_after=2):
    tn = _telnet_login(olt)
    output_parts = []
    try:
        _telnet_send_command(tn, 'enable', delay=1)
        _telnet_send_command(tn, 'config', delay=1)
        for cmd in commands:
            if cmd:
                out = _telnet_send_command(tn, cmd, delay=delay_after)
                output_parts.append(out)
        _telnet_send_command(tn, 'quit', delay=1)
    finally:
        try:
            tn.close()
        except:
            pass
    return '\n'.join(output_parts)


def _ssh_shell(olt, commands, delay_after=2):
    params = _get_netmiko_params(olt)
    conn = ConnectHandler(**params)
    conn.enable()
    conn.config_mode()
    output_parts = []
    for cmd in commands:
        if cmd:
            out = conn.send_command(cmd, read_timeout=delay_after + 10)
            time.sleep(1)
            output_parts.append(out)
    conn.disconnect()
    return '\n'.join(output_parts)


def _shell(olt, commands, delay_after=2):
    try:
        return _ssh_shell(olt, commands, delay_after)
    except Exception:
        return _telnet_shell(olt, commands, delay_after)


def check_olt_status(olt):
    for port in (22, 23):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(3)
        try:
            sock.connect((olt.ip, port))
            sock.close()
            return {'status': 'online', 'port': port}
        except:
            pass
    return {'status': 'offline'}


def execute_command(olt, command):
    try:
        params = _get_netmiko_params(olt)
        conn = ConnectHandler(**params)
        conn.enable()
        output = conn.send_command(command, delay=2)
        conn.disconnect()
        return output
    except Exception:
        return _telnet_shell(olt, [command], delay_after=2)


def get_olt_config(olt):
    cmd = 'display current-configuration' if olt.type == 'Huawei' else 'show running-config'
    return execute_command(olt, cmd)


def scan_unregistered(olt):
    out = _shell(olt, ['display ont autofind all'])
    results = []
    regex = re.compile(r'F/S/P\s+:\s+(\d+)/(\d+)/(\d+)[\s\S]*?Ont SN\s+:\s+([A-Z0-9]+)')
    for m in regex.finditer(out):
        results.append({'slot': m.group(2), 'pon': m.group(3), 'sn': m.group(4)})
    if not results:
        lines = out.split('\n')
        for line in lines:
            parts = line.strip().split()
            if len(parts) >= 4 and re.match(r'^\d+/\d+/\d+$', parts[1]):
                port_parts = parts[1].split('/')
                results.append({'slot': port_parts[1], 'pon': port_parts[2], 'sn': parts[3]})
    return results


def provision_ont(olt, slot, pon, sn, vlan, nama, alamat='',
                  pppoe_user='', pppoe_pass='', additional_vlans='',
                  use_tr069=False, tr069_profile='acs'):
    nama_clean = re.sub(r'[^a-zA-Z0-9]', '_', nama)[:32]
    line_profile = olt.line_profile_id or '10'
    srv_profile = olt.srv_profile_id or '10'

    out_existing = _shell(olt, [f'interface gpon 0/{slot}', f'display ont info {pon} all', 'quit'])

    used_ids = set()
    for m in re.finditer(r'O[NT]+[\s-]*ID\s*:\s*(\d+)', out_existing, re.I):
        used_ids.add(int(m.group(1)))

    if not used_ids:
        for m in re.finditer(r'^\s*\d+/\s*\d+/\d+\s+(\d+)\s+[A-F0-9]+', out_existing, re.M):
            used_ids.add(int(m.group(1)))

    next_id = 0
    for i in range(128):
        if i not in used_ids:
            next_id = i
            break

    add_out = _shell(olt, [
        f'interface gpon 0/{slot}',
        f'ont add {pon} {next_id} sn-auth {sn} omci ont-lineprofile-id {line_profile} ont-srvprofile-id {srv_profile} desc "{nama_clean}"',
        'quit'
    ], delay_after=5)

    add_ok = re.search(r'success\s*:\s*[1-9]', add_out)
    if not add_ok:
        return {'status': 'error', 'log': f'Gagal daftarkan ONT:\n{add_out}', 'raw_output': add_out}

    sp_out = _shell(olt, [
        f'service-port vlan {vlan} gpon 0/{slot}/{pon} ont {next_id} gemport 1 multi-service user-vlan {vlan}',
        ''
    ], delay_after=3)

    sp_ok = not re.search(r'(% Bad|% Unrecognized|Error:|Failure:)', sp_out, re.I)
    if not sp_ok:
        return {'status': 'error', 'log': f'Service-port gagal:\n{sp_out}', 'raw_output': sp_out}

    if pppoe_user and pppoe_pass:
        _shell(olt, [
            f'interface gpon 0/{slot}',
            f'ont ipconfig {pon} {next_id} pppoe vlan {vlan} user-account username "{pppoe_user}" password "{pppoe_pass}"',
            'quit'
        ])

    if additional_vlans:
        extra = [v.strip() for v in additional_vlans.split(',') if v.strip()]
        for ev in extra:
            if ev == vlan:
                continue
            _shell(olt, [
                f'service-port vlan {ev} gpon 0/{slot}/{pon} ont {next_id} gemport 1 multi-service user-vlan {ev}',
                ''
            ], delay_after=2)

    if use_tr069:
        _shell(olt, [
            f'interface gpon 0/{slot}',
            f'ont ipconfig {pon} {next_id} dhcp vlan 100',
            'quit'
        ])

    extra_arr = [v.strip() for v in additional_vlans.split(',') if v.strip()] if additional_vlans else []
    if use_tr069 and '100' not in extra_arr:
        extra_arr.append('100')
    all_vlans = ','.join(filter(None, [vlan] + extra_arr))

    return {
        'status': 'success',
        'ont_id': next_id,
        'tr069': bool(use_tr069),
        'all_vlans': all_vlans
    }


def delete_ont_from_olt(olt, slot, pon, ont_id):
    sp_output = _shell(olt, [
        f'display service-port port 0/{slot}/{pon} ont {ont_id}',
        ''
    ])
    sp_ids = []
    for m in re.finditer(r'^\s*(\d{1,5})\s+', sp_output, re.M):
        sp_ids.append(int(m.group(1)))
    sp_ids = list(set(sp_ids))

    cmds = []
    for sp_id in sp_ids:
        cmds.append(f'undo service-port {sp_id}')
    cmds.append(f'interface gpon 0/{slot}')
    cmds.append(f'ont delete {pon} {ont_id}')
    cmds.append('quit')
    cmds.append('save')

    return _shell(olt, cmds, delay_after=3)


def get_ont_optical_info(olt, slot, pon, ont_id):
    out = _shell(olt, [
        f'interface gpon 0/{slot}',
        f'display ont optical-info {pon} {ont_id}',
        'quit'
    ])
    m = re.search(r'Rx\s+optical\s+power\(dBm\)\s*:\s*([-0-9.]+)', out, re.I)
    return (m.group(1) + ' dBm') if m else None


def get_onts_optical_info(olt, onts):
    results = {}
    valid = [o for o in onts if o.get('ont_id') is not None]
    if not valid:
        return results

    slot = valid[0]['slot']
    cmds = [f'interface gpon 0/{slot}']
    for ont in valid:
        cmds.append(f'display ont optical-info {ont["pon"]} {ont["ont_id"]}')
    cmds.append('quit')

    output = _shell(olt, cmds, delay_after=2)
    for ont in valid:
        key = f'{ont["slot"]}/{ont["pon"]}/{ont["ont_id"]}'
        cmd_str = f'display ont optical-info {ont["pon"]} {ont["ont_id"]}'
        idx = output.find(cmd_str)
        if idx == -1:
            results[key] = None
            continue
        after = output[idx + len(cmd_str):]
        m = re.search(r'Rx\s+optical\s+power\(dBm\)\s*:\s*([-0-9.]+)', after, re.I)
        results[key] = (m.group(1) + ' dBm') if m else None
    return results


def get_onts_vlan_info(olt, onts):
    results = {}
    valid = [o for o in onts if o.get('ont_id') is not None]
    if not valid:
        return results

    cmds = []
    for ont in valid:
        cmds.append(f'display service-port port 0/{ont["slot"]}/{ont["pon"]} ont {ont["ont_id"]}')
        cmds.append('')
    output = _shell(olt, cmds, delay_after=2)

    for ont in valid:
        key = f'{ont["slot"]}/{ont["pon"]}/{ont["ont_id"]}'
        cmd_str = f'display service-port port 0/{ont["slot"]}/{ont["pon"]} ont {ont["ont_id"]}'
        idx = output.find(cmd_str)
        if idx == -1:
            results[key] = None
            continue
        after = output[idx + len(cmd_str):]
        m = re.search(r'^\s*\d+\s+(\d+)\s+', after, re.M)
        results[key] = m.group(1) if m else None
    return results


def get_registered_onts(olt, slot, pon):
    raw = _shell(olt, [f'interface gpon 0/{slot}', f'display ont info {pon} all', 'quit'])
    print(f'[DEBUG] Raw output from OLT {olt.ip} slot {slot} pon {pon}:')
    print(raw)

    def parse_onts(output):
        onts = []
        for m in re.finditer(r'O[NT]+[\s-]*ID\s*:\s*(\d+)[\s\S]*?SN\s*:\s*(\S+)', output, re.I):
            onts.append({'ont_id': int(m.group(1)), 'sn': m.group(2), 'status': 'online'})
        if not onts:
            for m in re.finditer(r'^\s*\d+/\s*\d+/\d+\s+(\d+)\s+([A-F0-9]+)\s+(\S+)', output, re.M):
                onts.append({'ont_id': int(m.group(1)), 'sn': m.group(2), 'status': m.group(3)})
        for m in re.finditer(r'^\s*\d+/\s*\d+/\d+\s+(\d+)\s+(.+)$', output, re.M):
            oid = int(m.group(1))
            desc = m.group(2).strip()
            for o in onts:
                if o['ont_id'] == oid:
                    o['description'] = desc
        return onts

    onts = parse_onts(raw)
    if not onts:
        return [], raw

    rx_map = get_onts_optical_info(olt, [{'slot': slot, 'pon': pon, 'ont_id': o['ont_id']} for o in onts])
    vlan_map = get_onts_vlan_info(olt, [{'slot': slot, 'pon': pon, 'ont_id': o['ont_id']} for o in onts])

    result = []
    for ont in onts:
        key = f'{slot}/{pon}/{ont["ont_id"]}'
        result.append({
            'ont_id': ont['ont_id'],
            'sn': ont['sn'],
            'slot': slot,
            'pon': pon,
            'description': ont.get('description', ''),
            'vlan': vlan_map.get(key, ''),
            'rx_power': rx_map.get(key, None),
            'status': ont.get('status', 'online'),
        })
    return result, raw


def configure_tr069(olt, slot, pon, ont_id, profile='acs'):
    out = _shell(olt, [
        f'interface gpon 0/{slot}',
        f'ont ipconfig {pon} {ont_id} dhcp vlan 100',
        'quit'
    ])
    has_error = bool(re.search(r'(% Bad|% Unrecognized|Error:|Failure:)', out, re.I))
    if has_error:
        return {'status': 'error', 'log': f'TR069 config failed:\n{out}', 'raw_output': out}
    return {'status': 'success', 'profile': profile, 'log': out}

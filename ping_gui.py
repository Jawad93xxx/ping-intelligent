#!/usr/bin/env python3
# ping_gui.py - Ping Intelligent (Windows) - GUI léger avec historique
# Dépendances: PySimpleGUI
import PySimpleGUI as sg
import subprocess, socket, threading, datetime, csv, re, os, sys, platform
from shutil import which

DEFAULT_COUNT = 4
DEFAULT_TIMEOUT_MS = 2000
MAX_HISTORY = 200

def resolve_host(hostname):
    try:
        infos = socket.getaddrinfo(hostname, None, socket.AF_INET)
        if infos:
            return infos[0][4][0]
    except:
        pass
    try:
        return socket.gethostbyname(hostname)
    except:
        return None

def run_ping_command(host, count=DEFAULT_COUNT, timeout_ms=DEFAULT_TIMEOUT_MS):
    """
    Execute the system ping command and return a dict:
      { status: bool, resolved_ip: str, avg_ms: int|None, loss_pct: int|None, raw: str }
    On Windows, the ping process is started with CREATE_NO_WINDOW to avoid the black console window.
    """
    resolved = resolve_host(host)

    # Build command depending on OS
    if platform.system().lower().startswith("win"):
        cmd = ["ping", "-n", str(count), "-w", str(timeout_ms), host]
    else:
        timeout_sec = max(1, int((timeout_ms + 999) // 1000))
        cmd = ["ping", "-c", str(count), "-W", str(timeout_sec), host]

    try:
        # On Windows, prevent a console window from appearing
        if platform.system().lower().startswith("win") and hasattr(subprocess, "CREATE_NO_WINDOW"):
            creationflags = subprocess.CREATE_NO_WINDOW
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=(count * (timeout_ms / 1000.0) + 5),
                creationflags=creationflags
            )
        else:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=(count * (timeout_ms / 1000.0) + 5)
            )
        out = proc.stdout + proc.stderr
    except Exception as e:
        out = f"ERROR: {e}"
        return {"status": False, "resolved_ip": resolved or "N/A", "avg_ms": None, "loss_pct": None, "raw": out}

    # Parse times (cross-locale handling)
    times = []
    for m in re.finditer(r'(?:time|temps)[=<]\s*([0-9]+)\s*ms', out, flags=re.IGNORECASE):
        try:
            times.append(int(m.group(1)))
        except:
            pass
    if not times:
        for m in re.finditer(r'(?:time|temps)[=<]\s*<?\s*([0-9]+)\s*ms', out, flags=re.IGNORECASE):
            try:
                times.append(int(m.group(1)))
            except:
                pass

    # Average parsing (Windows localized output or fallback to calculated mean)
    avg = None
    mavg = re.search(r'(?:Average|Moyenne)\s*=\s*([0-9]+)\s*ms', out, flags=re.IGNORECASE)
    if mavg:
        try:
            avg = int(mavg.group(1))
        except:
            avg = None

    # Loss percent - try to parse a trailing "%" then fallback to Received/Sent or counts
    loss_pct = None
    all_pct = re.findall(r'([0-9]{1,3})\s*%', out)
    if all_pct:
        try:
            loss_pct = int(all_pct[-1])
        except:
            loss_pct = None

    if avg is None and times:
        try:
            avg = int(sum(times) / len(times))
        except:
            avg = None

    # Windows "Received = X" parsing (localized variants)
    m_received = re.search(r'(?:Received|Reçus)\s*=\s*([0-9]+)', out, flags=re.IGNORECASE)
    m_sent = re.search(r'(?:Sent|Envoyé|Envoyes|Envoyés)\s*=\s*([0-9]+)', out, flags=re.IGNORECASE)
    if m_received:
        try:
            rec = int(m_received.group(1))
            sent = int(m_sent.group(1)) if m_sent else int(count)
            loss_pct = int(round((1 - rec / sent) * 100))
        except:
            pass

    if loss_pct is None:
        try:
            recv = len(times)
            loss_pct = int(round((1 - (recv / count)) * 100))
        except:
            loss_pct = None

    status_online = False
    if loss_pct is not None:
        status_online = (loss_pct < 100)
    else:
        status_online = bool(times)

    if not resolved:
        mr = re.search(r'Reply from\s*([\d\.]+)', out)
        if mr:
            resolved = mr.group(1)
    resolved = resolved or "N/A"

    return {"status": status_online, "resolved_ip": resolved, "avg_ms": avg, "loss_pct": loss_pct, "raw": out}

def make_window():
    sg.theme("SystemDefault")
    header = [[sg.Text("Ping Intelligent", font=("Segoe UI", 16, "bold"))]]
    input_row = [
        sg.Text("Adresse (IP/domaine):"), sg.Input(key="-HOST-", size=(30,1)),
        sg.Button("Ping", key="-PING-", bind_return_key=True),
        sg.Text("Count:"), sg.Spin([1,2,3,4,5,10,20], initial_value=DEFAULT_COUNT, key="-COUNT-", size=(5,1)),
        sg.Text("Timeout(ms):"), sg.Input(DEFAULT_TIMEOUT_MS, key="-TIMEOUT-", size=(7,1))
    ]
    result_frame = [
        [sg.Text("Statut:"), sg.Text("", key="-STATUS-", size=(4,1), font=("Segoe UI", 12, "bold"))],
        [sg.Text("IP résolue:"), sg.Text("", key="-RESOLVED-")],
        [sg.Text("Latence moyenne (ms):"), sg.Text("", key="-AVG-")],
        [sg.Text("Perte (%):"), sg.Text("", key="-LOSS-")],
        [sg.Text("Date / Heure:"), sg.Text("", key="-TIME-")],
        [sg.Multiline("", key="-RAW-", size=(80,8), disabled=True, autoscroll=True)]
    ]
    history_headings = ["#","Date/Heure","Host","IP","Status","Avg(ms)","Loss(%)"]
    history_table = [[sg.Table(values=[], headings=history_headings, key="-TABLE-", auto_size_columns=False, col_widths=[4,18,20,14,6,8,8], num_rows=8)]]
    bottom_row = [sg.Button("Exporter CSV", key="-EXPORT-"), sg.Button("Effacer historique", key="-CLEAR-"), sg.Text("", key="-MSG-", size=(40,1), justification='right'), sg.Button("Quitter", key="-QUIT-")]
    layout = [[sg.Column(header)], [sg.HorizontalSeparator()], input_row, [sg.Frame("Résultat", result_frame)], [sg.Frame("Historique récent", history_table)], bottom_row]
    return sg.Window("Ping Intelligent", layout, finalize=True)

history = []
worker_lock = threading.Lock()
worker_running = False

def do_ping_and_update(window, host, count, timeout_ms):
    global worker_running
    with worker_lock:
        worker_running = True
    try:
        res = run_ping_command(host, count=count, timeout_ms=timeout_ms)
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        row = {
            "time": now,
            "host": host,
            "ip": res.get("resolved_ip","N/A"),
            "status": "✅" if res.get("status") else "❌",
            "avg": res.get("avg_ms") if res.get("avg_ms") is not None else "N/A",
            "loss": res.get("loss_pct") if res.get("loss_pct") is not None else "N/A",
            "raw": res.get("raw","")
        }
        history.insert(0, row)
        if len(history) > MAX_HISTORY:
            history.pop()
        window.write_event_value("-PING-DONE-", row)
    finally:
        with worker_lock:
            worker_running = False

def export_history_csv(path):
    try:
        with open(path, "w", newline='', encoding='utf-8') as f:
            w = csv.writer(f)
            w.writerow(["datetime","host","ip","status","avg_ms","loss_pct"])
            for r in history:
                w.writerow([r["time"], r["host"], r["ip"], r["status"], r["avg"], r["loss"]])
        return True, None
    except Exception as e:
        return False, str(e)

def main():
    if which("ping") is None:
        sg.popup_error("Commande 'ping' introuvable sur ce système.")
        sys.exit(1)
    win = make_window()
    while True:
        event, values = win.read(timeout=100)
        if event == sg.WIN_CLOSED or event == "-QUIT-":
            break
        if event == "-PING-":
            host = values.get("-HOST-", "").strip()
            if not host:
                win["-MSG-"].update("Entrez une adresse ou un domaine.")
                continue
            try:
                count = int(values.get("-COUNT-", DEFAULT_COUNT))
            except:
                count = DEFAULT_COUNT
            try:
                timeout_ms = int(values.get("-TIMEOUT-", DEFAULT_TIMEOUT_MS))
            except:
                timeout_ms = DEFAULT_TIMEOUT_MS
            if worker_running:
                win["-MSG-"].update("Un ping est déjà en cours...")
                continue
            win["-MSG-"].update("Lancement du ping...")
            win["-STATUS-"].update("...")
            win["-RESOLVED-"].update("")
            win["-AVG-"].update("")
            win["-LOSS-"].update("")
            win["-TIME-"].update("")
            win["-RAW-"].update("")
            t = threading.Thread(target=do_ping_and_update, args=(win, host, count, timeout_ms), daemon=True)
            t.start()
        if event == "-PING-DONE-":
            row = values[event]
            win["-STATUS-"].update(row["status"])
            win["-RESOLVED-"].update(row["ip"])
            win["-AVG-"].update(row["avg"])
            win["-LOSS-"].update(row["loss"])
            win["-TIME-"].update(row["time"])
            win["-RAW-"].update(row["raw"])
            table_vals = []
            for idx, r in enumerate(history[:MAX_HISTORY]):
                table_vals.append([idx+1, r["time"], r["host"], r["ip"], r["status"], r["avg"], r["loss"]])
            win["-TABLE-"].update(values=table_vals)
            win["-MSG-"].update("Ping terminé.")
        if event == "-EXPORT-":
            fname = sg.popup_get_file("Enregistrer CSV", save_as=True, file_types=(("CSV Files","*.csv"),), default_extension="csv")
            if fname:
                ok, err = export_history_csv(fname)
                if ok:
                    sg.popup("Historique exporté :", fname)
                else:
                    sg.popup_error("Erreur export CSV :", err)
        if event == "-CLEAR-":
            if sg.popup_yes_no("Effacer l'historique ?") == "Yes":
                history.clear()
                win["-TABLE-"].update(values=[])
                win["-MSG-"].update("Historique effacé.")
    win.close()

if __name__ == "__main__":
    main()
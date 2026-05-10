Dim shell, appDir, pythonCmd
Set shell = CreateObject("WScript.Shell")

appDir = "C:\Users\duric\market-analyzer"

' Avvia Flask in una finestra minimizzata
shell.Run "cmd /k python """ & appDir & "\app.py""", 2, False

' Attendi che Flask sia pronto
WScript.Sleep 4000

' Apri il browser
shell.Run "http://127.0.0.1:5000"

Set shell = CreateObject("WScript.Shell")
shell.CurrentDirectory = "D:\WhisperFlow"
shell.Run "cmd /c C:\Users\ASUS\AppData\Local\Programs\Python\Python312\pythonw.exe whisperflow.py > whisperflow.log 2>&1", 0, False

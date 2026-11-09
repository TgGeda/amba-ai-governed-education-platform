from __future__ import annotations
from pathlib import Path
from PySide6.QtCore import QObject,QProcess,Signal
import sys
class ReadinessManager(QObject):
 operation_started=Signal(str);operation_output=Signal(str);operation_completed=Signal(str,int);operation_failed=Signal(str,str);busy_changed=Signal(bool)
 def __init__(self,root:Path,parent:QObject|None=None):super().__init__(parent);self.root=root;self._process=None;self._name=''
 def generate_reflection(self):self._start('readiness reflection',['tools/readiness/generate_readiness_reflection.py'])
 def generate_evidence_plan(self):self._start('evidence closure plan',['tools/readiness/generate_readiness_evidence_plan.py'])
 def generate_closure_evidence(self):self._start('closure evidence',['tools/readiness/generate_closure_evidence.py'])
 def apply_verified_closure(self):self._start('verified readiness closure',['tools/readiness/apply_verified_readiness_closure.py'])
 def _start(self,name,args):
  if self._process:return
  p=QProcess(self);p.setWorkingDirectory(str(self.root));env=p.processEnvironment();env.insert('PYTHONPATH',str(self.root/'src'));p.setProcessEnvironment(env);p.readyReadStandardOutput.connect(self._read);p.readyReadStandardError.connect(self._read);p.finished.connect(self._done);p.errorOccurred.connect(self._error);self._process=p;self._name=name;self.busy_changed.emit(True);self.operation_started.emit(name);p.start(sys.executable,args)
 def _read(self):
  if self._process:
   text=(bytes(self._process.readAllStandardOutput())+bytes(self._process.readAllStandardError())).decode('utf-8','replace')
   if text:self.operation_output.emit(text)
 def _done(self,code,status):name=self._name;self._read();self._process=None;self._name='';self.busy_changed.emit(False);self.operation_completed.emit(name,code)
 def _error(self,error):name=self._name;msg=self._process.errorString() if self._process else str(error);self._process=None;self._name='';self.busy_changed.emit(False);self.operation_failed.emit(name,msg)

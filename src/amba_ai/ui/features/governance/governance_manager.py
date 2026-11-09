from __future__ import annotations
from pathlib import Path
import sys
from PySide6.QtCore import QObject,QProcess,Signal
from .artifact_loader import load_dashboard_snapshot
class GovernanceManager(QObject):
 snapshot_loaded=Signal(object);load_failed=Signal(str);operation_started=Signal(str);operation_output=Signal(str);operation_completed=Signal(str,int);operation_failed=Signal(str,str);busy_changed=Signal(bool)
 def __init__(self,root:Path,parent:QObject|None=None):
  super().__init__(parent);self.root=root;self._process:QProcess|None=None;self._operation=''
 def refresh(self):
  try:self.snapshot_loaded.emit(load_dashboard_snapshot(self.root))
  except Exception as exc:self.load_failed.emit(str(exc))
 def run_four_scenarios(self):self._start('four-scenario demonstration',['-m','amba_ai.cli.evidence_chain_demo'])
 def verify_manifest(self):self._start('submission manifest verification',['tools/submission/verify_submission_manifest.py'])
 def generate_y3172_mapping(self):self._start('Y.3172 mapping generation',['tools/standards/generate_y3172_mapping.py'])
 def generate_agent_architecture(self):self._start('agent architecture generation',['tools/submission/generate_agent_architecture.py'])
 def _start(self,name:str,args:list[str]):
  if self._process is not None:return
  process=QProcess(self);process.setWorkingDirectory(str(self.root));env=process.processEnvironment();env.insert('PYTHONPATH',str(self.root/'src'));process.setProcessEnvironment(env);process.readyReadStandardOutput.connect(self._read);process.readyReadStandardError.connect(self._read);process.finished.connect(self._finished);process.errorOccurred.connect(self._failed);self._process=process;self._operation=name;self.busy_changed.emit(True);self.operation_started.emit(name);process.start(sys.executable,args)
 def _read(self):
  if self._process is None:return
  text=(bytes(self._process.readAllStandardOutput())+bytes(self._process.readAllStandardError())).decode('utf-8','replace')
  if text:self.operation_output.emit(text)
 def _finished(self,code:int,status):
  name=self._operation;self._read();self._process=None;self._operation='';self.busy_changed.emit(False);self.operation_completed.emit(name,code)
  if code==0:self.refresh()
 def _failed(self,error):
  name=self._operation;message=self._process.errorString() if self._process else str(error);self._process=None;self._operation='';self.busy_changed.emit(False);self.operation_failed.emit(name,message)

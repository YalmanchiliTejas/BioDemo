"""Separate bounded worker running only fixed ingestion/analysis functions."""
import resource
import fcntl
import os
import signal
import sys
from .cases import CaseService


if __name__=='__main__':
    resource.setrlimit(resource.RLIMIT_CPU,(150,150))
    resource.setrlimit(resource.RLIMIT_FSIZE,(512*1024*1024,512*1024*1024))
    signal.alarm(max(1,min(600,int(os.getenv('PHARMA_JOB_SECONDS','180')))))
    service=CaseService(sys.argv[1]); ident,lease=sys.argv[2:4]
    folder=service.root/'case-job-locks'; folder.mkdir(exist_ok=True,mode=0o700)
    with (folder/(ident+'.lock')).open('a+') as lock:
        try: fcntl.flock(lock.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            with service.connect() as con: con.execute("UPDATE pharma_jobs SET status='failed',error='Prior worker still active; retry after it exits' WHERE id=? AND lease=?",(ident,lease))
        else: service.execute(ident,lease)

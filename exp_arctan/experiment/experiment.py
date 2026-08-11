from .transcript import Transcript


ONGOING_EXPERIMENT = None



class Experiment:
    def __init__(self, title: str="Experiment", parameters: dict={}, verbose: str="normal"):
        self.title = title
        self.parameters = parameters
        self.exit_code = 0
        self.verbose = verbose

        
    def __enter__(self):
        self.transcript = Transcript(
            self.title,
            verbose=self.verbose
        )
        self.transcript.start()
        global ONGOING_EXPERIMENT
        ONGOING_EXPERIMENT = self
        return self
    

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        self.finish()
        return False

    
    def finish(self) -> None:
        self.transcript.finish()
        
        
    def fail(self, reason: str) -> None:
        self.exit_code = 1
        self.transcript.fail(reason)



def progress_bar(iterated_over, title: str="loop"):
    for x in ONGOING_EXPERIMENT.transcript.progress_bar(iterated_over, title=title):
        yield x
    
    
def section(title: str) -> None:
    ONGOING_EXPERIMENT.transcript.section(title)
    
def subsection(title: str) -> None:
    ONGOING_EXPERIMENT.transcript.subsection(title)
    
def subsubsection(title: str) -> None:
    ONGOING_EXPERIMENT.transcript.subsubsection(title)

def warning(reason:str="") -> None:
    ONGOING_EXPERIMENT.transcript.warning(reason)

def debug(reason:str="") -> None:
    ONGOING_EXPERIMENT.transcript.debug(reason)

def fail(reason:str="") -> None:
    ONGOING_EXPERIMENT.fail(reason)

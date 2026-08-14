from .transcript import Transcript
from .parameters import get_cli_args

ONGOING_EXPERIMENT = None


class Experiment:
    def __init__(
            self,
            title: str="Experiment",
            parameters: list[tuple]=[],
            description: str="<set `description` parameter at initialization>",
            verbose: str="normal"
    ):
        self.title = title
        self.parameters = parameters
        self.description = description
        self.exit_code = 0
        
    def __enter__(self):
        self.parameters_values = get_cli_args(self.parameters, self.title, self.description)
        self.verbose = self.parameters_values.verbose

        self.transcript = Transcript(
            self.title,
            verbose=self.verbose,
            description=self.description,
            logfile="./log.log"
        )
        self.transcript.start()
        print("Parameters:")
        for name, value in vars(self.parameters_values).items():
            print(f"- {name} = {value}")

        
        global ONGOING_EXPERIMENT
        ONGOING_EXPERIMENT = self

        # !TODO! print current git commit 
        
        return self
    

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        self.finish()
        return False

    
    def finish(self) -> None:
        self.transcript.finish()
        
        
    def fail(self, reason: str) -> None:
        self.exit_code = 1
        self.transcript.fail(reason)

        
    def good(self, reason: str) -> None:
        self.transcript.good(reason)


    def check_if(self, predicate: bool, description: str) -> None:
        if predicate:
            self.good("{" + description + "} holds")
        else:
            self.fail("{" + description + "} DOES NOT hold")

            
    def check_if_equality(self, v1, v2, description: str=""):
        if v1 == v2:
            self.good(f"{v1} == {v2} {description}")
        else:
            self.fail(f"{v1} != {v2} {description}")

            
    def check_if_strictly_smaller(self, v, bound, description: str=""):
        if v < bound:
            self.good(f"{v} < {bound} {description}")
        else:
            self.fail(f"{v} >= {bound} {description}")

            
            


# !SECTION! Wrapping the ongoing experiment

def experiment_parameters():
    return ONGOING_EXPERIMENT.parameters_values

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

def good(reason:str="") -> None:
    ONGOING_EXPERIMENT.good(reason)

def check_if(predicate: bool, description: str) -> None:
    ONGOING_EXPERIMENT.check_if(predicate, description)

def check_if_equality(v1, v2, description: str=""):
    ONGOING_EXPERIMENT.check_if_equality(v1, v2, description)

def check_if_strictly_smaller(v, bound, description: str=""):
    ONGOING_EXPERIMENT.check_if_strictly_smaller(v, bound, description)

def exit_code() -> int:
    return ONGOING_EXPERIMENT.exit_code

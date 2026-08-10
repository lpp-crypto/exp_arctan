from time import sleep

from exp_arctan import *


if __name__ == "__main__":
    with Experiment("Some experiment without a markdown file",
                    verbose="normal"):
        section("first section")
        print({0: 1, 2: "bla"})
        print("bli")
        debug("debugging data")
        fail("oh well.")
        sleep(2)
        print("blo")
        
              

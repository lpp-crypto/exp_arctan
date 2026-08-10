from exp_arctan import *


if __name__ == "__main__":
    with Experiment("Some experiment without a markdown file",
                    verbose="debug"):
        section("first section")
        print({0: 1, 2: "bla"})
        print("bli")
        debug("debugging data")
        fail("oh well.")
        print("blo")
        
              

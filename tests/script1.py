from time import sleep

from exp_arctan import *


if __name__ == "__main__":
    with Experiment("Some experiment without a markdown file",
                    verbose="normal"):
        
        section("first section")
        
        subsection("first subsection")
        
        print({0: 1, 2: "bla"})
        print("bli")
        debug("debugging data")
        fail("oh well.")
        sleep(1)

        subsection("second subsection")
        
        print("blo")
        
        section("and now for something completely different")

        subsection("and now we sleep, but in a loop")

        print("we sleep again")
        for x in progress_bar(range(0, 10), "sleeping iterations"):
            print(x)
            sleep(0.3)
        
              

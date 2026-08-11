from time import sleep
import itertools

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
        sleep(1.5)

        subsection("second subsection")
        
        print("blo")
        
        section("and now for something completely different")

        subsection("and now we sleep, but in a loop")

        print("we sleep again")
        for x in progress_bar(range(0, 10), "sleeping iterations"):
            print("iteration", x)
            sleep(0.3)
        
        subsection("same, but we don't know the number of iterations a priori")

        for x, y in progress_bar(itertools.product(range(0, 3), range(0,3)),
                              "other sleeping iterations"):
            print("iteration", x, y)
            sleep(0.3)
              

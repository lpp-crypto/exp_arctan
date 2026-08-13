from time import sleep
import itertools
from random import randint

from exp_arctan import *


if __name__ == "__main__":
    with Experiment("Some experiment without a markdown file",
                    description="Testing if the `Experiment` class does what it is supposed to do",
                    parameters=[
                        ("n", 3, "some numerical parameter"),
                        ("t", 2.0, "another numerical parameter"),
                    ]):
        
        section("first section")
        
        subsection("first subsection")

        ep = experiment_parameters()
        print("n*t =", ep.n * ep.t)
        print({0: 1, 2: "bla"})
        print("bli")
        debug("debugging data")

        subsection("testing `check_if`")
        
        for x in range(0, 10):
            v = randint(0, 9)
            check_if_strictly_smaller(v, 5, "random value that should be small")

        subsection("third subsection")
        
        print("blo")
        sleep(1.5)
        
        section("and now for something completely different")

        subsection("and now we sleep, but in a loop")

        print("we sleep again")
        for x in progress_bar(range(0, ep.n), "n sleeping iterations"):
            print("iteration", x)
            sleep(0.3)
        
        subsection("same, but we don't know the number of iterations a priori")

        for x, y in progress_bar(itertools.product(range(0, int(ep.t)), range(0, int(ep.t))),
                              "more sleeping iterations"):
            print("iteration", x, y)
            sleep(0.3)
              

from threading import Thread

def task_1():
    for i in range(1,101):
        i+=i
        print("task 1 is in process")
    print("The sum of numbers is:",i)

def task_2():
    for i in range(1,101):
        if i%2==0:
            i+=i
    print("The sum of even numbers is:",i)
def task_3():
    for i in range(1,101):
        if i%2!=0:
            i+=i
    print("The sum of odd numbers is:",i)

t = Thread(target=task_1)
t1 = Thread(target=task_2)
t2 = Thread(target=task_3)
t.start()       
t1.start()
t2.start()

t.join()
t1.join()
t2.join()

exec(open('proto10.py').read().split('for W in')[0])
for W, a, pen in ((2,0.2,0.15),(2,0.2,0.2),(2,0.3,0.2),(1,0.1,0.1),(2,0.1,0.1),(3,0.15,0.15),(4,0.2,0.2)):
    print(W, a, pen, full(lambda q: posd(smooth(q, W, a), pen)), flush=True)

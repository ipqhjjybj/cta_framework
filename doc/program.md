



examples/run_turtle.py  这是你唯一可以修改的文件

总共按如下步骤迭代3次
    
    1. 修改 examples/run_turtle.py， 为了拿到跟高的share，对策略进行改动，但是只做微小改动
    2. 运行 examples/run_turtle.py， 得到回测结果
    3. cat results/turtle/report.html | grep "Sharpe Ratio",  查看得到 这次改动后的策略sharpe
    4. 如果 这次改动 Sharpe Ratio 值得到提升，  那么 git commit && git push  保存这次结果
    5. 如果 这次改动 Sharpe Ratio 下降，  那么 git reset 回到 上次改动的位置




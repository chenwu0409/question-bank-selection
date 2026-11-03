# -*- coding: utf-8 -*-
"""独立验算工具：分数精确的常用计算，避免手算误差；平台答案不可得时用来自算。

用法：
  python verify_calc.py --case lever --G 2 --n1 3 --L1 2 --n2 3
  python verify_calc.py --case quad --a -1 --b -2 --c 3
  python verify_calc.py --case area_max --points "0,3;-2,0;4,-1;6,0" --xs "-2,6"
  python verify_calc.py --case shoelace --points "0,3;-2,0;4,-1;6,0"

说明：
  - 全部用 fractions.Fraction 精确分数，不用浮点，避免末位误差。
  - 结果是「独立验算」，不等于平台官方答案；与平台冲突时以平台为准并记录冲突。

依赖：仅标准库。
"""
import io
import sys
import json
import argparse
from fractions import Fraction as F
from math import isqrt

if __name__ == '__main__':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')


def frac(x):
    return F(str(x))


def fmt(v):
    """把 Fraction 显示成整数或分数，不显示 Fraction(...) 包装"""
    if not isinstance(v, F):
        return str(v)
    if v.denominator == 1:
        return str(v.numerator)
    return '%s/%s' % (v.numerator, v.denominator)


def exact_sqrt(disc):
    """判别式是完全平方时返回精确 Fraction 根，否则返回 float 近似"""
    if disc < 0:
        return None
    n, d = disc.numerator, disc.denominator
    rn, rd = isqrt(n), isqrt(d)
    if rn * rn == n and rd * rd == d:
        return F(rn, rd)
    return float(disc) ** 0.5


def shoelace(points):
    """鞋带公式求多边形面积（points 为 [(x,y), ...] 闭多边形顶点）"""
    s = F(0)
    n = len(points)
    for i in range(n):
        x1, y1 = points[i]
        x2, y2 = points[(i + 1) % n]
        s += x1 * y2 - x2 * y1
    return abs(s) / 2


def case_lever(a):
    """杠杆平衡：n1*g*L1 = n2*g*L2 → 求所需力 F = n1*g*L1/L2"""
    G = frac(a.G)
    n1 = frac(a.n1)
    L1 = frac(a.L1)
    L2 = frac(a.L2)
    torque = n1 * G * L1
    F = torque / L2
    print('阻力矩 = n1*G*L1 = %s * %s * %s = %s N·格' % (fmt(n1), fmt(G), fmt(L1), fmt(torque)))
    print('所需动力 F = 阻力矩 / L2 = %s / %s = %s N' % (fmt(torque), fmt(L2), fmt(F)))
    print('校验 F*L2 = %s，阻力矩 = %s，%s'
          % (fmt(F * L2), fmt(torque), '一致' if F * L2 == torque else '不一致'))
    return F


def case_quad(a):
    """一元二次：顶点、零点、对称轴"""
    A = frac(a.a)
    B = frac(a.b)
    C = frac(a.c)
    if A == 0:
        print('a 不能为 0')
        return None
    xv = -B / (2 * A)
    yv = A * xv * xv + B * xv + C
    print('对称轴 x = %s' % fmt(xv))
    print('顶点 (%s, %s)' % (fmt(xv), fmt(yv)))
    disc = B * B - 4 * A * C
    if disc < 0:
        print('判别式 = %s < 0，无实根' % fmt(disc))
    elif disc == 0:
        print('判别式 = 0，唯一根 x = %s' % fmt(-B / (2 * A)))
    else:
        sq = exact_sqrt(disc)
        r1 = (-B + sq) / (2 * A)
        r2 = (-B - sq) / (2 * A)
        print('判别式 = %s，根 x1 = %s，x2 = %s' % (fmt(disc), fmt(r1), fmt(r2)))
    print('顶点纵坐标 %s（%s）' % (fmt(yv), '最大值' if A < 0 else '最小值'))
    return xv


def case_area_max(a):
    """面积关于 x 的一次函数 S = k*x + b 在区间 [x0,x1] 上的极值"""
    k = frac(a.k)
    b = frac(a.b)
    x0 = frac(a.x0)
    x1 = frac(a.x1)
    print('S(x) = %s*x + %s，区间 [%s, %s]' % (fmt(k), fmt(b), fmt(x0), fmt(x1)))
    if k == 0:
        print('面积恒为 %s' % fmt(b))
        return b
    xv = -b / k
    if x0 <= xv <= x1:
        print('顶点 x = %s 在区间内，S = %s（%s）'
              % (fmt(xv), fmt(k * xv + b), '最大值' if k < 0 else '最小值'))
        return k * xv + b
    best = max(x0, x1, key=lambda x: k * x + b)
    print('区间内极值在 x = %s，S = %s' % (fmt(best), fmt(k * best + b)))
    return k * best + b


def case_shoelace(a):
    pts = []
    for p in a.points.split(';'):
        x, y = p.split(',')
        pts.append((frac(x), frac(y)))
    s = shoelace(pts)
    print('顶点：', [(fmt(x), fmt(y)) for x, y in pts])
    print('面积 = %s' % fmt(s))
    return s


def main():
    ap = argparse.ArgumentParser(description='独立验算工具（分数精确）')
    ap.add_argument('--case', required=True,
                    choices=['lever', 'quad', 'area_max', 'shoelace'])
    ap.add_argument('--G', default=1)
    ap.add_argument('--n1', default=1)
    ap.add_argument('--L1', default=1)
    ap.add_argument('--L2', default=1)
    ap.add_argument('--a', default=1)
    ap.add_argument('--b', default=0)
    ap.add_argument('--c', default=0)
    ap.add_argument('--k', default=0)
    ap.add_argument('--x0', default=0)
    ap.add_argument('--x1', default=1)
    ap.add_argument('--points', default='')
    args = ap.parse_args()

    if args.case == 'lever':
        case_lever(args)
    elif args.case == 'quad':
        case_quad(args)
    elif args.case == 'area_max':
        case_area_max(args)
    elif args.case == 'shoelace':
        case_shoelace(args)


if __name__ == '__main__':
    main()

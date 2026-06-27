#!/bin/sh
#
#SBATCH --partition=compute
#SBATCH --account=education-eemcs-msc-cs
#SBATCH --time=00:10:00
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=6
#SBATCH --mem-per-cpu=2G
#SBATCH --job-name="astor-test"

module load 2025
module load julia

srun <executable>
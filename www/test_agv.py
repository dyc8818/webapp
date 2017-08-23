import sys
argv = sys.argv[1:]
print(argv)
if not argv:
        print('Usage: ./pymonitor your-script.py')
        exit(0)
if argv[0] != 'python':
        argv.insert(0, 'python')

print(argv)
.PHONY: test demo clean

test:
	python3 -m unittest discover -s tests -v

demo:
	bash scripts/demo.sh

clean:
	rm -rf build bin/genhtml

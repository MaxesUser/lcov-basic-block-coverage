.PHONY: test demo publish clean

test:
	python3 -m unittest discover -s tests -v

demo:
	bash scripts/demo.sh

publish:
	python3 scripts/publish_reports.py

clean:
	rm -rf build bin/genhtml

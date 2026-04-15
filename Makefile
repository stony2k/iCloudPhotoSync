all:
	@echo "Nothing to compile"

install:
	mkdir -p $(DESTDIR)/ui
	cp -a ui/* $(DESTDIR)/ui/

clean:
	@echo "Nothing to clean"

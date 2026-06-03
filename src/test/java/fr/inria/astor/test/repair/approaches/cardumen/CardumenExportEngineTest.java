package fr.inria.astor.test.repair.approaches.cardumen;

import java.io.File;
import java.nio.file.Files;
import java.util.List;

import org.junit.Test;

import fr.inria.astor.approaches.cardumen.CardumenExportEngine;
import fr.inria.astor.test.repair.core.BaseEvolutionaryTest;
import fr.inria.main.AstorOutputStatus;
import fr.inria.main.CommandSummary;
import fr.inria.main.evolution.AstorMain;

import static org.junit.Assert.*;

/**
 * Tests for {@link CardumenExportEngine}.
 * <p>
 * Uses the chart_11 example (ShapeUtilities) which ships with pre-built
 * class files, matching the setup used in {@link CardumenApproachTest}.
 */
public class CardumenExportEngineTest extends BaseEvolutionaryTest {

	static final File BUG_DIR = new File("./examples/chart_11/").getAbsoluteFile();

	/** Builds a CommandSummary pre-configured for chart_11. */
	private static CommandSummary chart11Command() {
		String depJunit = new File("./lib/junit-4.11.jar").getAbsolutePath();
		String bugLocation = BUG_DIR.getAbsolutePath();

		CommandSummary cmd = new CommandSummary();
		cmd.command.put("-mode", "custom");
		cmd.command.put("-customengine", CardumenExportEngine.class.getName());
		cmd.command.put("-id", "Chart-11");
		cmd.command.put("-location", bugLocation);
		cmd.command.put("-srcjavafolder", "source");
		cmd.command.put("-srctestfolder", "tests");
		cmd.command.put("-binjavafolder", "build");
		cmd.command.put("-bintestfolder", "build-tests");
		cmd.command.put("-failing", "org.jfree.chart.util.junit.ShapeUtilitiesTests");
		cmd.command.put("-dependencies",
				bugLocation + "/lib/servlet.jar" + File.pathSeparator
				+ bugLocation + "/lib/itext-2.0.6.jar" + File.pathSeparator
				+ depJunit);
		cmd.command.put("-seed", "0");
		cmd.command.put("-scope", "local");
		cmd.command.put("-population", "1");
		cmd.command.put("-javacompliancelevel", "4");
		cmd.command.put("-flthreshold", "0.1");
		cmd.command.put("-maxtime", "60");
		return cmd;
	}

	@Test
	public void testExportFilesAreCreated() throws Exception {
		AstorMain main = new AstorMain();
		main.execute(chart11Command().flat());

		CardumenExportEngine engine = (CardumenExportEngine) main.getEngine();
		assertEquals(AstorOutputStatus.EXHAUSTIVE_NAVIGATED, engine.getOutputStatus());

		File templates  = new File(BUG_DIR, "templates.txt");
		File context    = new File(BUG_DIR, "context.txt");
		File target     = new File(BUG_DIR, "target_type.txt");
		File hierarchy  = new File(BUG_DIR, "type_hierarchy.txt");

		assertTrue("templates.txt should exist",        templates.exists());
		assertTrue("context.txt should exist",          context.exists());
		assertTrue("target_type.txt should exist",      target.exists());
		assertTrue("type_hierarchy.txt should exist",   hierarchy.exists());

		assertTrue("templates.txt should be non-empty",   templates.length() > 0);
		assertTrue("context.txt should be non-empty",     context.length()   > 0);
		assertTrue("target_type.txt should be non-empty", target.length()    > 0);
	}

	@Test
	public void testTargetTypeFileContents() throws Exception {
		AstorMain main = new AstorMain();
		main.execute(chart11Command().flat());

		List<String> lines = Files.readAllLines(new File(BUG_DIR, "target_type.txt").toPath());
		String content = String.join("\n", lines);

		assertTrue("should contain class field",          content.contains("class:"));
		assertTrue("should contain line field",           content.contains("line:"));
		assertTrue("should contain suspiciousness field", content.contains("suspiciousness:"));
		assertTrue("should contain element field",        content.contains("element:"));
		assertTrue("should contain type field",           content.contains("type:"));

		// The suspicious class for chart_11 is ShapeUtilities
		assertTrue("class should reference ShapeUtilities",
				content.contains("ShapeUtilities"));
	}

	@Test
	public void testContextFileContents() throws Exception {
		AstorMain main = new AstorMain();
		main.execute(chart11Command().flat());

		List<String> lines = Files.readAllLines(new File(BUG_DIR, "context.txt").toPath());
		String content = String.join("\n", lines);

		assertTrue("should have Variables section",
				content.contains("# Variables in scope"));
		assertTrue("should have enclosing class methods section",
				content.contains("# Methods of enclosing class"));
		assertTrue("should have reachable methods section",
				content.contains("# Methods reachable via in-scope variables"));
		assertTrue("should have fields section",
				content.contains("# Fields of in-scope variables"));

		// Every data line (non-blank, non-comment) must end with
		// " : <globalCount> : <localCount>", with localCount <= globalCount.
		int dataLines = 0;
		for (String line : lines) {
			if (line.isEmpty() || line.startsWith("#")) continue;
			dataLines++;

			int lastSep = line.lastIndexOf(" : ");
			assertTrue("line should contain at least one ' : ' separator: " + line, lastSep >= 0);
			int prevSep = line.lastIndexOf(" : ", lastSep - 1);
			assertTrue("line should contain at least two ' : ' separators (for global and local counts): " + line,
					prevSep >= 0);

			String localStr  = line.substring(lastSep + 3).trim();
			String globalStr = line.substring(prevSep + 3, lastSep).trim();

			int global, local;
			try {
				global = Integer.parseInt(globalStr);
				local  = Integer.parseInt(localStr);
			} catch (NumberFormatException e) {
				fail("trailing two fields should be integers, got global='" + globalStr
						+ "' local='" + localStr + "' in line: " + line);
				return;
			}
			assertTrue("counts should be non-negative in line: " + line, global >= 0 && local >= 0);
			assertTrue("local count should not exceed global count in line: " + line, local <= global);
		}
		assertTrue("context.txt should contain at least one data line", dataLines > 0);
	}

	@Test
	public void testTypeHierarchyFileFormat() throws Exception {
		AstorMain main = new AstorMain();
		main.execute(chart11Command().flat());

		List<String> lines = Files.readAllLines(new File(BUG_DIR, "type_hierarchy.txt").toPath());
		for (String line : lines) {
			if (line.trim().isEmpty()) continue;
			// Each line must be: SimpleName -> (extends|implements) -> qualified.Name
			String[] parts = line.split(" -> ");
			assertEquals("each line should have exactly 3 parts: " + line, 3, parts.length);
			assertTrue("middle part must be 'extends' or 'implements': " + line,
					parts[1].equals("extends") || parts[1].equals("implements"));
		}
	}

	@Test
	public void testJuliaToolReturnsCandidates() throws Exception {
		String home = System.getProperty("user.home");
		System.setProperty("cardumen.julia.tool",    home + "/thesis/herb/find2fix.jl");
		System.setProperty("cardumen.julia.project", home + "/thesis/herb");
		try {
			AstorMain main = new AstorMain();
			main.execute(chart11Command().flat());

			CardumenExportEngine engine = (CardumenExportEngine) main.getEngine();
			assertFalse("Julia tool should return at least one candidate",
					engine.getLastCandidates().isEmpty());
		} finally {
			System.clearProperty("cardumen.julia.tool");
			System.clearProperty("cardumen.julia.project");
		}
	}

	@Test
	public void testTemplatesFileContainsTypedEntries() throws Exception {
		AstorMain main = new AstorMain();
		main.execute(chart11Command().flat());

		List<String> lines = Files.readAllLines(new File(BUG_DIR, "templates.txt").toPath());

        assertFalse("templates.txt should have at least one entry", lines.isEmpty());

		// ExpressionTypeIngredientSpace writes entries in the format:
		//   templateCode -> SpoonASTClass -> returnType -> qualifiedClassName -> packageName -> count
		//   ###
		// Each entry is terminated by "###" on its own line, allowing
		// multi-line template code. Split on "###" and assert each entry
		// contains exactly five " -> " separators and that the trailing
		// field parses as a positive integer (the template's frequency).
		String content = String.join("\n", lines);
		String[] entries = content.split("###");
		for (String entry : entries) {
			if (entry.trim().isEmpty()) continue;
			int sep1 = entry.indexOf(" -> ");
			int sep2 = entry.indexOf(" -> ", sep1 + 1);
			int sep3 = entry.indexOf(" -> ", sep2 + 1);
			int sep4 = entry.indexOf(" -> ", sep3 + 1);
			int sep5 = entry.indexOf(" -> ", sep4 + 1);
			assertTrue("each entry should contain at least five ' -> ' separators: " + entry, sep5 >= 0);
			assertTrue("each entry should contain exactly five ' -> ' separators: " + entry,
					entry.indexOf(" -> ", sep5 + 1) < 0);

			String countField = entry.substring(sep5 + 4).trim();
			int count;
			try {
				count = Integer.parseInt(countField);
			} catch (NumberFormatException e) {
				fail("trailing field should be an integer count, got '" + countField + "' in entry: " + entry);
				return;
			}
			assertTrue("count should be positive, got " + count + " in entry: " + entry, count > 0);
		}
	}
}

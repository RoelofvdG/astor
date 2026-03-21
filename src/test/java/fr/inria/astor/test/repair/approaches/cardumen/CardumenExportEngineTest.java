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

	/** Builds a CommandSummary pre-configured for chart_11. */
	private static CommandSummary chart11Command() {
		String depJunit = new File("./lib/junit-4.11.jar").getAbsolutePath();
		String bugLocation = new File("./examples/chart_11/").getAbsolutePath();

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

		File templates = new File("templates.txt");
		File context  = new File("context.txt");
		File target   = new File("target_type.txt");

		assertTrue("templates.txt should exist",   templates.exists());
		assertTrue("context.txt should exist",     context.exists());
		assertTrue("target_type.txt should exist", target.exists());

		assertTrue("templates.txt should be non-empty", templates.length() > 0);
		assertTrue("context.txt should be non-empty",   context.length()  > 0);
		assertTrue("target_type.txt should be non-empty", target.length() > 0);
	}

	@Test
	public void testTargetTypeFileContents() throws Exception {
		AstorMain main = new AstorMain();
		main.execute(chart11Command().flat());

		List<String> lines = Files.readAllLines(new File("target_type.txt").toPath());
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

		List<String> lines = Files.readAllLines(new File("context.txt").toPath());
		String content = String.join("\n", lines);

		assertTrue("should have Variables section",
				content.contains("# Variables in scope"));
		assertTrue("should have enclosing class methods section",
				content.contains("# Methods of enclosing class"));
		assertTrue("should have reachable methods section",
				content.contains("# Methods reachable via in-scope variables"));
	}

	@Test
	public void testTemplatesFileContainsTypedEntries() throws Exception {
		AstorMain main = new AstorMain();
		main.execute(chart11Command().flat());

		List<String> lines = Files.readAllLines(new File("templates.txt").toPath());

        assertFalse("templates.txt should have at least one entry", lines.isEmpty());

		// ExpressionTypeIngredientSpace writes entries in the format:
		//   templateCode -> SpoonASTClass -> returnType
		//   ###
		// Each entry is terminated by "###" on its own line, allowing
		// multi-line template code. Split on "###" and assert each entry
		// contains exactly two " -> " separators.
		String content = String.join("\n", lines);
		String[] entries = content.split("###");
		for (String entry : entries) {
			if (entry.trim().isEmpty()) continue;
			int first = entry.indexOf(" -> ");
			int second = entry.indexOf(" -> ", first + 1);
			assertTrue("each entry should contain at least two ' -> ' separators: " + entry, second >= 0);
			assertTrue("each entry should contain exactly two ' -> ' separators: " + entry,
					entry.indexOf(" -> ", second + 1) < 0);
		}
	}
}
